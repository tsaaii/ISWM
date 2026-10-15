"""Remote camera view: lets someone far from the site watch the cameras, using
very little internet.

The plant PC sits behind the plant's router, so it cannot be reached from
outside. Instead it asks the relay (the cloud_api service on Cloud Run) every
``poll_seconds`` whether anyone is watching. That question is a few hundred
bytes. Only while a viewer has the remote page open does the plant send small
JPEG pictures of the watched camera(s); when the viewer leaves, sending stops
within seconds. The relay decides size, quality and pictures per second.
"""
import json
import logging
import threading
import time

try:
    import cv2
except ImportError:
    cv2 = None


class RemoteView:
    def __init__(self, service):
        self.svc = service
        self.state = "off"     # off | waiting | sending | offline | error
        self.message = None
        self.bytes = 0
        self.watching = []
        self._session = None
        self._stop = threading.Event()

    def cfg(self):
        return self.svc.settings.get("remote") or {}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="remote-view").start()

    def stop(self):
        self._stop.set()

    def status(self):
        return {"state": self.state, "message": self.message, "kb": round(self.bytes / 1024), "watching": self.watching}

    def _http(self):
        if self._session is None:
            import requests
            self._session = requests.Session()  # keeps one connection open between questions (less data)
        return self._session

    def _base(self, cfg):
        return cfg["relay_url"].rstrip("/") + "/v1/plant/" + self.svc.cloud.site_id()

    def _loop(self):
        while not self._stop.is_set():
            cfg = self.cfg()
            if not (cfg.get("enabled") and cfg.get("relay_url") and cfg.get("site_key")):
                self.state, self.watching = "off", []
                self._stop.wait(30)
                continue
            try:
                ask = self.ask(cfg)
                if ask.get("cams"):
                    self.send(cfg, ask)
                else:
                    self.state, self.watching = "waiting", []
                    self._stop.wait(max(10, int(cfg.get("poll_seconds") or 20)))
            except Exception as e:
                self.state, self.message, self.watching = "offline", str(e)[:160], []
                self._stop.wait(min(300, 4 * max(10, int(cfg.get("poll_seconds") or 20))))

    def ask(self, cfg):
        r = self._http().get(self._base(cfg) + "/wanted", headers={"X-Site-Key": cfg["site_key"],
                                                                     "X-Cams": self.cam_names(),
                                                                     "X-Status": self.health()}, timeout=15)
        self.bytes += len(r.content) + 300  # + request and headers, roughly
        if r.status_code == 401:
            self.state, self.message = "error", "Relay refused the site key."
            raise RuntimeError(self.message)
        r.raise_for_status()
        self.message = None
        return r.json()

    def health(self):
        """How the plant is doing, for the dashboard's status board (about 200 bytes, sent with each check-in)."""
        from . import __version__
        wb = self.svc.wb.live()
        cams = self.svc.cams.status()
        problems = [c["label"] for c in cams.values() if c.get("error") and c["error"] != "Not set up"]
        try:
            queued = len(self.svc.db.queue_waiting())
        except Exception:
            queued = None
        return json.dumps({"ver": __version__, "wb": bool(wb.get("connected")), "kg": wb.get("weight"),
                           "stable": bool(wb.get("stable")), "cams": len(cams), "cam_problems": problems[:8],
                           "queued": queued, "sync": self.svc.cloud.state, "operator": self.svc.operator})

    def cam_names(self):
        """Camera ids and the names the admin gave them (e.g. "Tipping floor"), so the remote page shows them.
        A few hundred bytes; sent with every question and picture so a rename shows up within seconds."""
        return json.dumps([[n, self.svc.cams.label(n)] for n in self.svc.cams.ordered()])

    def picture(self, cam, width, quality):
        frame = cam.frame()
        if frame is None or cv2 is None:
            return None
        h, w = frame.shape[:2]
        if w > width:
            frame = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else None

    def send(self, cfg, ask):
        """Send pictures until nobody is watching any more."""
        headers = {"X-Site-Key": cfg["site_key"], "Content-Type": "image/jpeg"}
        self.state = "sending"
        while ask.get("cams") and not self._stop.is_set():
            self.watching = ask["cams"]
            for name in ask["cams"]:
                cam = self.svc.cams.cams.get(name)
                if cam is None:
                    continue
                cam.demand(8)  # camera runs only while someone watches
                jpg = self.picture(cam, int(ask.get("width") or 640), int(ask.get("quality") or 60))
                if jpg is None:
                    continue
                wb = self.svc.wb.live()
                headers["X-Cams"] = self.cam_names()
                headers["X-Weight"] = json.dumps({"connected": wb["connected"], "weight": wb["weight"],
                                                  "stable": wb["stable"]})
                r = self._http().post(self._base(cfg) + "/frame/" + name, data=jpg, headers=headers, timeout=15)
                self.bytes += len(jpg) + 400
                r.raise_for_status()
                ask = r.json()
            time.sleep(1.0 / max(0.2, float(ask.get("fps") or 1)))
            if not any(c.frame() is not None for c in self.svc.cams.cams.values()):
                ask = self.ask(cfg)  # cameras still starting: keep asking so we notice if the viewer left
        self.watching = []
        logging.info("remote view: viewer left, stopped sending (%d KB so far)", self.bytes // 1024)

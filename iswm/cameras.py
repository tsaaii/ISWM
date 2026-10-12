"""Plant cameras: front and back, plus up to six more the admin adds.

Capture is adapted from adex_lite's camera.py (USB index, RTSP or HTTP
camera, reconnect on failure) and the photo watermark from its
add_watermark(). Picture quality is better than adex_lite because:

  * RTSP uses the camera's main stream (brand presets pick it), over TCP so
    lost UDP packets don't smear the picture, and nothing is forced down to
    640x480 the way adex_lite did;
  * saved photos come from the full-resolution frame, or better, from the
    camera's own JPEG snapshot (ISAPI / snapshot.cgi) when one is set, which
    has no video-compression blur; they are written at JPEG quality 95;
  * USB cameras are asked for 1920x1080 MJPG instead of 640x480;
  * only the on-screen preview is shrunk (to keep the UI light).

Cameras run only on demand (no constant streaming): while an operator has
"View live" on, for two minutes after a vehicle is picked (so the photo is
ready at Save), or while the admin preview / live-view page is watching.
Otherwise the stream is closed. With a snapshot endpoint set, Save takes the
photo straight from the camera without opening the video stream at all.
"""
import os
import sys
import threading
import time
import urllib.request

# FFmpeg options must be in place before the first RTSP open.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|max_delay;500000")

try:
    import cv2
    import numpy as np
except ImportError:  # app still runs; cameras show "No signal"
    cv2 = None
    np = None

from .settings import camera_address, camera_urls

STALE_AFTER_S = 5.0
PREVIEW_WIDTH = 960
PREVIEW_EVERY_S = 0.1
PHOTO_QUALITY = 95


def fetch_jpeg(url, user="", password="", timeout=4):
    """Download one JPEG with Basic or Digest login (Hikvision/Dahua use Digest)."""
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    if user:
        mgr.add_password(None, url, user, password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr),
                                         urllib.request.HTTPBasicAuthHandler(mgr))
    with opener.open(url, timeout=timeout) as r:
        data = r.read()
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise IOError("Camera did not send a picture")
    return frame


class Camera:
    def __init__(self, name, cfg):
        self.name = name
        self.cfg = dict(cfg)
        self._lock = threading.Lock()
        self._frame = None
        self._jpeg = None
        self._at = 0.0
        self._enc_at = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        self.size = None
        self._want_until = 0.0
        self._woke = threading.Event()

    def demand(self, seconds):
        """Keep the camera running for at least ``seconds`` more."""
        self._want_until = max(self._want_until, time.monotonic() + seconds)
        self._woke.set()

    def wanted(self):
        return time.monotonic() < self._want_until

    def start(self):
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="camera-" + self.name)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None

    def restart(self, cfg):
        self.stop()
        self.cfg = dict(cfg)
        with self._lock:
            self._frame, self._jpeg, self._at, self.size = None, None, 0.0, None
        self.start()

    def live(self):
        return self._jpeg is not None and time.monotonic() - self._at < STALE_AFTER_S

    def jpeg(self):
        with self._lock:
            return self._jpeg if self.live() else None

    def frame(self):
        with self._lock:
            return None if self._frame is None or not self.live() else self._frame.copy()

    def photo(self, wait=8.0):
        """Best picture for a saved photo: the camera's own snapshot if set, else a frame from the stream
        (starting the stream briefly if it was off)."""
        _, snap = camera_urls(self.cfg)
        if snap and cv2 is not None:
            try:
                return fetch_jpeg(snap, self.cfg.get("username") or "", self.cfg.get("password") or "", timeout=3)
            except Exception as e:
                self.error = "Snapshot failed, used video frame: " + str(e)[:120]
        if (self.cfg.get("type") or "USB").upper() == "NONE" or not (self._thread and self._thread.is_alive()):
            return None
        if self.error and not self.live():
            wait = min(wait, 1.5)  # camera already failing: don't hold up Save
        self.demand(20)
        end = time.monotonic() + wait
        while time.monotonic() < end:
            f = self.frame()
            if f is not None:
                return f
            time.sleep(0.1)
        return None

    def _set(self, frame):
        now = time.monotonic()
        with self._lock:
            self._frame, self._at = frame, now
            self.size = (frame.shape[1], frame.shape[0])
        if now - self._enc_at < PREVIEW_EVERY_S and self._jpeg is not None:
            return
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)), interpolation=cv2.INTER_AREA) \
            if w > PREVIEW_WIDTH else frame
        ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            with self._lock:
                self._jpeg, self._enc_at = buf.tobytes(), now

    def _open(self, kind, url):
        if kind in ("RTSP", "HTTP"):
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        else:
            idx = int(self.cfg.get("index") or 0)
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(idx)
            # MJPG lets USB cameras send full HD; their default (YUY2) is often 640x480.
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _loop(self):
        if cv2 is None:
            self.error = "OpenCV missing"
            return
        kind = (self.cfg.get("type") or "USB").upper()
        if kind == "NONE":
            self.error = "Not set up"
            return
        url, snap = camera_urls(self.cfg)
        if kind in ("RTSP", "HTTP") and not url:
            self.error = "Type the camera IP address"
            return
        user, pw = self.cfg.get("username") or "", self.cfg.get("password") or ""
        poll_jpeg = None  # HTTP: None = not checked yet, True = endpoint gives single JPEGs (polled), False = video
        cap, fails = None, 0
        while not self._stop.is_set():
            if not self.wanted():  # nobody needs the picture: close the stream, use no network
                if cap is not None:
                    cap.release()
                    cap = None
                with self._lock:
                    self._frame, self._jpeg = None, None
                self._woke.wait(1.0)
                self._woke.clear()
                continue
            try:
                if kind == "HTTP" and poll_jpeg is None:
                    try:
                        self._set(fetch_jpeg(_strip_auth(url), user, pw))
                        poll_jpeg = True
                    except Exception:
                        poll_jpeg = False
                if poll_jpeg:
                    self._set(fetch_jpeg(_strip_auth(url), user, pw))
                    self.error, fails = None, 0
                    self._stop.wait(0.2)
                    continue
                if cap is None or not cap.isOpened():
                    cap = self._open(kind, url)
                    if not cap.isOpened():
                        if kind == "HTTP":
                            poll_jpeg = True
                            continue
                        raise IOError("Camera did not open. Check IP, port, user, password and endpoint.")
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise IOError("No picture from camera")
                self._set(frame)
                self.error, fails = None, 0
            except Exception as e:
                self.error = str(e)[:200]
                fails += 1
                if cap is not None:
                    cap.release()
                    cap = None
                self._stop.wait(min(10.0, 1.0 + fails))
        if cap is not None:
            cap.release()


def _strip_auth(url):
    """http://user:pw@host/... -> http://host/... (credentials go through the auth handler)."""
    scheme, _, rest = url.partition("://")
    host, slash, path = rest.partition("/")
    return scheme + "://" + host.split("@")[-1] + slash + path


def watermark(image, lines, ticket_id=None):
    """Adapted from adex_lite camera.add_watermark: text lines at top, ticket at bottom."""
    out = image.copy()
    h, w = out.shape[:2]
    font, scale, white = cv2.FONT_HERSHEY_SIMPLEX, max(0.5, w / 1280 * 0.8), (255, 255, 255)
    thick = max(2, int(round(w / 700)))
    sizes = [cv2.getTextSize(t, font, scale, thick)[0] for t in lines]
    if lines:
        box_h = sum(s[1] for s in sizes) + 10 * len(lines) + 12
        overlay = out.copy()
        cv2.rectangle(overlay, (0, 0), (max(s[0] for s in sizes) + 20, box_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, out, 0.4, 0, out)
        y = 6
        for t, s in zip(lines, sizes):
            y += s[1] + 10
            cv2.putText(out, t, (10, y), font, scale, white, thick)
    if ticket_id:
        text = "Ticket: " + ticket_id
        (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
        overlay = out.copy()
        cv2.rectangle(overlay, (0, h - th - 20), (tw + 20, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, out, 0.4, 0, out)
        cv2.putText(out, text, (10, h - 10), font, scale, white, thick)
    return out


class Cameras:
    """All cameras of the plant: front and back, plus any the admin added."""

    def __init__(self, cfg):
        self.cams = {}
        self._cfg = {}
        self.configure(cfg)

    def configure(self, cfg):
        from .settings import camera_ids
        self._cfg = dict(cfg)
        for name in camera_ids(cfg):
            if name not in self.cams:
                self.cams[name] = Camera(name, cfg[name])

    def ordered(self):
        from .settings import camera_ids
        return [n for n in camera_ids(self._cfg) if n in self.cams]

    def label(self, name):
        return (self._cfg.get(name) or {}).get("label") or name.capitalize() + " camera"

    def start(self):
        for c in self.cams.values():
            c.start()

    def stop(self):
        for c in self.cams.values():
            c.stop()

    def restart(self, cfg):
        """Apply new settings: restart changed cameras, start new ones, stop removed ones."""
        for name in [n for n in self.cams if n not in cfg]:
            self.cams.pop(name).stop()
        old = {n: dict(c.cfg) for n, c in self.cams.items()}
        self.configure(cfg)
        for name, c in self.cams.items():
            if name not in old:
                c.start()
            elif old[name] != dict(cfg[name]):
                c.restart(cfg[name])

    def status(self):
        """Every camera in screen order (front, back, then added ones)."""
        out = {}
        for name in self.ordered():
            c, cfg = self.cams[name], self._cfg.get(name) or {}
            out[name] = {"live": c.live(), "error": c.error, "size": c.size, "on": c.wanted(),
                         "label": self.label(name), "show": cfg.get("show", True), "photo": cfg.get("photo", True),
                         "type": (cfg.get("type") or "USB").upper(), "addr": camera_address(cfg)}
        return out

    def demand(self, seconds, names=None):
        for n, c in self.cams.items():
            if names is None or n in names:
                c.demand(seconds)

    def _photo_cams(self):
        return [n for n in self.ordered() if (self._cfg.get(n) or {}).get("photo", True)]

    def demand_for_photo(self, seconds):
        """A vehicle was picked: warm up only cameras that need the video stream for their photo.
        Cameras with a snapshot endpoint give the photo directly, with no stream at all."""
        for n in self._photo_cams():
            c = self.cams[n]
            if not camera_urls(c.cfg)[1]:
                c.demand(seconds)

    def grab(self):
        """Best pictures from the photo cameras, taken at the same moment (None where a camera is down)."""
        out = {}
        names = self._photo_cams()
        threads = [threading.Thread(target=lambda n=n: out.__setitem__(n, self.cams[n].photo())) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=12)
        return {n: out.get(n) for n in names}

    def write(self, frames, folder, stem, lines, ticket_id):
        """Save grabbed frames as watermarked JPEGs. Returns {camera: path or None}."""
        out = {}
        for name, frame in frames.items():
            if frame is None or cv2 is None:
                out[name] = None
                continue
            path = os.path.join(folder, "%s_%s.jpg" % (stem, name))
            img = watermark(frame, lines + [self.label(name)], ticket_id)
            ok = cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), PHOTO_QUALITY])
            out[name] = path if ok else None
        return out

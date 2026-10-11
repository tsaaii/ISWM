"""Front and back cameras.

Capture is adapted from adex_lite's camera.py (USB index, RTSP URL or HTTP
snapshot URL through OpenCV; small buffer; reconnect on failure) and the
photo watermark from its add_watermark(). Each camera keeps its newest frame;
the UI shows it as an MJPEG stream and Save writes a watermarked JPEG.
"""
import os
import sys
import threading
import time
import urllib.request

try:
    import cv2
    import numpy as np
except ImportError:  # app still runs; cameras show "No signal"
    cv2 = None
    np = None

STALE_AFTER_S = 5.0


class Camera:
    def __init__(self, name, cfg):
        self.name = name
        self.cfg = dict(cfg)
        self._lock = threading.Lock()
        self._frame = None
        self._jpeg = None
        self._at = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.error = None

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
            self._frame, self._jpeg, self._at = None, None, 0.0
        self.start()

    def live(self):
        return self._jpeg is not None and time.monotonic() - self._at < STALE_AFTER_S

    def jpeg(self):
        with self._lock:
            return self._jpeg if self.live() else None

    def frame(self):
        with self._lock:
            return None if self._frame is None or not self.live() else self._frame.copy()

    def _set(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            with self._lock:
                self._frame, self._jpeg, self._at = frame, buf.tobytes(), time.monotonic()

    def _open(self):
        kind = (self.cfg.get("type") or "USB").upper()
        if kind == "RTSP":
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
            cap = cv2.VideoCapture(self.cfg.get("url") or "", cv2.CAP_FFMPEG)
        else:
            idx = int(self.cfg.get("index") or 0)
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(idx)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
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
        cap, fails = None, 0
        while not self._stop.is_set():
            try:
                if kind == "HTTP":
                    with urllib.request.urlopen(self.cfg.get("url") or "", timeout=3) as r:
                        data = np.frombuffer(r.read(), dtype=np.uint8)
                    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                    if frame is None:
                        raise IOError("Bad image from camera")
                    self._set(frame)
                    self.error, fails = None, 0
                    self._stop.wait(0.2)
                    continue
                if cap is None or not cap.isOpened():
                    cap = self._open()
                    if not cap.isOpened():
                        raise IOError("Camera did not open")
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


def watermark(image, lines, ticket_id=None):
    """Adapted from adex_lite camera.add_watermark: text lines at top, ticket at bottom."""
    out = image.copy()
    h, w = out.shape[:2]
    font, scale, white = cv2.FONT_HERSHEY_SIMPLEX, max(0.5, w / 1280 * 0.8), (255, 255, 255)
    thick = 2
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
    def __init__(self, cfg):
        self.cams = {name: Camera(name, cfg.get(name, {})) for name in ("front", "back")}

    def start(self):
        for c in self.cams.values():
            c.start()

    def stop(self):
        for c in self.cams.values():
            c.stop()

    def restart(self, cfg):
        for name, c in self.cams.items():
            c.restart(cfg.get(name, {}))

    def status(self):
        return {name: {"live": c.live(), "error": c.error} for name, c in self.cams.items()}

    def grab(self):
        """Current frames from both cameras (None where a camera is down)."""
        return {name: c.frame() for name, c in self.cams.items()}

    @staticmethod
    def write(frames, folder, stem, lines, ticket_id):
        """Save grabbed frames as watermarked JPEGs. Returns (front_path, back_path)."""
        out = []
        for name in ("front", "back"):
            frame = frames.get(name)
            if frame is None or cv2 is None:
                out.append(None)
                continue
            path = os.path.join(folder, "%s_%s.jpg" % (stem, name))
            img = watermark(frame, lines + [name.capitalize() + " camera"], ticket_id)
            ok = cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            out.append(path if ok else None)
        return tuple(out)

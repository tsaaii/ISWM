"""Local HTTP server between the screens and the Python side.

Listens on 127.0.0.1 only. Serves the web/ folder, camera streams at
/cam/<front|back>.mjpg, and JSON calls at POST /api/<method>. Every call
must carry the per-launch token, so another program or web page on the same
PC cannot drive the app.
"""
import http.server
import json
import mimetypes
import os
import secrets
import socketserver
import threading
import time
import traceback
import urllib.parse

from . import paths
from .db import RuleError

API = {"boot", "login", "logout", "live", "state", "vehicle_status", "vehicle_picked", "vehicle_cleared",
       "save_in", "save_out", "save_tare", "save_batch", "save_sample", "ask_correction", "retry_sync",
       "set_shifts", "report", "export_csv", "open_folder", "toggle_full", "setup", "admin_login", "admin_view",
       "admin_save", "admin_lock", "admin_set_logo", "admin_clear_logo", "admin_fix_entry",
       "admin_rename_vehicle", "admin_run_cleanup", "entry_history", "export_trips", "camera_watch",
       "settings_view", "settings_save"}
MAX_BODY = 4 * 1024 * 1024

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/webp", ".webp")


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def stream_mjpeg(handler, cam, interval=0.08, demand=False):
    """Send a camera as a multipart JPEG stream until the viewer leaves or the camera goes quiet."""
    handler.send_response(200)
    handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    try:
        last, idle_since = None, time.monotonic()
        while time.monotonic() - idle_since < (12 if demand else 5):  # camera gone: end the stream
            if demand:  # this viewer is what keeps the camera on
                cam.demand(5)
            jpg = cam.jpeg()
            if jpg is not None and jpg is not last:
                handler.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                    str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                last, idle_since = jpg, time.monotonic()
            time.sleep(interval)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        return


def make_handler(service, token, log_errors):
    web = os.path.realpath(paths.web_dir())

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype="application/json", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self, query):
            got = self.headers.get("X-ISWM-Token") or (query.get("t") or [""])[0]
            return secrets.compare_digest(got, token)

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == "/branding/logo":
                p = service.logo_path() if self._authorised(query) else None
                if not p:
                    return self._send(404, b"", "text/plain")
                with open(p, "rb") as f:
                    body = f.read()
                return self._send(200, body, mimetypes.guess_type(p)[0] or "image/png")
            if url.path.startswith("/photo/"):
                parts = url.path.split("/")
                p = service.photo_path(parts[2], parts[3]) if len(parts) == 4 and self._authorised(query) else None
                if not p:
                    return self._send(404, b"", "text/plain")
                with open(p, "rb") as f:
                    body = f.read()
                return self._send(200, body, "image/jpeg")
            if url.path.startswith("/cam/"):
                if not self._authorised(query):
                    return self._send(403, b"{}")
                return self._mjpeg(url.path[5:].split(".")[0])
            rel = urllib.parse.unquote(url.path.lstrip("/")) or "index.html"
            full = os.path.realpath(os.path.join(web, rel))
            if not full.startswith(web + os.sep) or not os.path.isfile(full):
                return self._send(404, b"Not found", "text/plain")
            with open(full, "rb") as f:
                body = f.read()
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            self._send(200, body, ctype)

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            name = url.path[len("/api/"):] if url.path.startswith("/api/") else ""
            if not self._authorised({}):
                return self._send(403, json.dumps({"error": "Forbidden"}).encode())
            if name not in API:
                return self._send(404, json.dumps({"error": "Unknown call"}).encode())
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise RuleError("That is too big.")
                args = json.loads(self.rfile.read(length) or b"{}") if length else {}
                result = getattr(service, name)(**args)
                body, code = json.dumps({"ok": True, "data": result}, default=str).encode(), 200
            except RuleError as e:
                body, code = json.dumps({"ok": False, "error": str(e)}).encode(), 200
            except Exception as e:
                if log_errors:
                    traceback.print_exc()
                body, code = json.dumps({"ok": False, "error": "Something went wrong: " + str(e)[:200]}).encode(), 500
            self._send(code, body)

        def _mjpeg(self, name):
            cam = service.cams.cams.get(name)
            if cam is None:
                return self._send(404, b"{}")
            stream_mjpeg(self, cam, demand=self.path.find("watch=1") >= 0)

    return Handler


def serve(service, port=0, log_errors=True):
    """Start the server in a background thread. Returns (url, token, server)."""
    token = secrets.token_urlsafe(24)
    httpd = _Server(("127.0.0.1", port), make_handler(service, token, log_errors))
    threading.Thread(target=httpd.serve_forever, daemon=True, name="http").start()
    url = "http://127.0.0.1:%d/index.html#t=%s" % (httpd.server_address[1], token)
    return url, token, httpd

"""Live view for other computers: a read-only page with the cameras, the live
weight and today's trips. Off until the admin turns it on and sets a viewer
password.

ISWM is the relay: it already holds each camera's stream, so viewers get the
small preview from ISWM instead of each one opening the camera. Cameras are
not loaded more as viewers are added, and the cameras' own passwords never leave
the plant PC.

Open from another PC on the same network:  http://<plant-pc-ip>:8090
User name: viewer   Password: the one set in admin.
"""
import base64
import html
import http.server
import json
import logging
import socketserver
import threading
import time
import datetime as dt

from .server import stream_mjpeg
from .settings import check_password

MAX_STREAMS = 16

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>%(site)s · live</title>
<style>
:root{--ink:#121A14;--muted:#33413A;--line:#CBD4CE;--green:#0E5230;--bg:#F2FBF4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Palatino Linotype",Palatino,Georgia,serif}
header{display:flex;align-items:center;gap:16px;padding:12px 20px;background:#fff;border-bottom:4px solid #1B8A3A}
header h1{font-size:22px;margin:0}header span{color:var(--muted)}
.pill{margin-left:auto;padding:4px 12px;border-radius:999px;font-weight:700;color:#fff;background:#C62828}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:16px;padding:16px 20px}
.cams{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.cam{position:relative;border-radius:14px;overflow:hidden;background:#C9CFCB;border:2px solid #9AA79F;aspect-ratio:16/9}
.cam img{width:100%%;height:100%%;object-fit:cover;display:block}
.cam b{position:absolute;left:10px;top:10px;padding:3px 10px;border-radius:999px;background:rgba(18,26,20,.6);color:#fff;font-size:13px}
.card{background:#fff;border:2px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:12px}
.big{font-size:56px;line-height:1;font-variant-numeric:tabular-nums}.small{color:var(--muted);font-size:14px}
table{width:100%%;border-collapse:collapse;font-size:15px}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left}
th{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}td.r,th.r{text-align:right}
.tot{display:flex;gap:18px}.tot div{flex:1}
@media (max-width:800px){main{grid-template-columns:1fr}}
</style></head><body>
<header><h1>%(site)s</h1><span>%(agency)s · live view</span><span id="wb" class="pill">…</span></header>
<main><section class="cams">
%(cams)s
</section><section>
<div class="card"><div class="small">Weighbridge</div><div><span id="w" class="big">—</span> kg</div><div id="st" class="small"></div></div>
<div class="card tot"><div><div class="small">Inward today</div><div id="tin" style="font-size:22px">—</div></div>
<div><div class="small">Outward today</div><div id="tout" style="font-size:22px">—</div></div></div>
<div class="card"><div class="small" style="margin-bottom:6px">Latest trips</div>
<table><thead><tr><th>Time</th><th>Ticket</th><th>Vehicle</th><th class="r">Net</th></tr></thead><tbody id="rows"></tbody></table></div>
</section></main>
<script>
function retry(img){setTimeout(function(){img.src=img.src.split('?')[0]+'?'+Date.now()},3000)}
function trips(n){return n+(n===1?' trip':' trips')}
function kg(n){return n==null?'Tare pending':Math.round(n).toLocaleString('en-IN')+' kg'}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function tick(){fetch('api/live').then(function(r){return r.json()}).then(function(d){
 var w=document.getElementById('wb');w.textContent=d.connected?'Bridge on':'Bridge off';w.style.background=d.connected?'#1B8A3A':'#C62828';
 document.getElementById('w').textContent=d.connected?Math.round(d.weight).toLocaleString('en-IN'):'—';
 document.getElementById('st').textContent=d.connected?(d.stable?'Steady':'Settling'):'Not connected';}).catch(function(){})}
function today(){fetch('api/today').then(function(r){return r.json()}).then(function(d){
 document.getElementById('tin').textContent=trips(d.in.trips)+' · '+kg(d.in.net);
 document.getElementById('tout').textContent=trips(d.out.trips)+' · '+kg(d.out.net);
 document.getElementById('rows').innerHTML=d.rows.map(function(r){return '<tr><td>'+esc(r.time)+'</td><td>'+esc(r.id)+'</td><td>'+esc(r.vno)+'</td><td class="r">'+esc(kg(r.net))+'</td></tr>'}).join('')}).catch(function(){})}
tick();today();setInterval(tick,700);setInterval(today,15000);
</script></body></html>"""


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LiveView:
    def __init__(self, service):
        self.svc = service
        self.httpd = None
        self.error = None
        self.streams = 0
        self._lock = threading.Lock()
        self._fails = {}

    def running(self):
        return self.httpd is not None

    def apply(self):
        """Start, stop or move the server to match the settings."""
        cfg = self.svc.settings.get("live_view") or {}
        want = bool(cfg.get("enabled")) and bool(cfg.get("password_hash"))
        port = int(cfg.get("port") or 8090)
        if self.httpd and (not want or self.httpd.server_address[1] != port):
            self.stop()
        if want and not self.httpd:
            try:
                self.httpd = _Server(("0.0.0.0", port), self._handler())
                threading.Thread(target=self.httpd.serve_forever, daemon=True, name="liveview").start()
                self.error = None
                logging.info("live view on port %d", port)
            except OSError as e:
                self.httpd, self.error = None, "Port %d is busy or blocked: %s" % (port, e)

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def _auth_ok(self, header, ip):
        n, until = self._fails.get(ip, (0, 0.0))
        if time.monotonic() < until:
            return False
        try:
            user, _, pw = base64.b64decode((header or "").split(" ", 1)[1]).decode().partition(":")
        except Exception:
            return False
        ok = user == "viewer" and check_password(pw, (self.svc.settings.get("live_view") or {}).get("password_hash"))
        if ok:
            self._fails.pop(ip, None)
        else:
            n += 1
            self._fails[ip] = (n, time.monotonic() + (60 if n >= 5 else 0))
        return ok

    def today(self):
        day = dt.date.today()
        rep = self.svc.db.report_daily(day)
        rows = self.svc.db.trips(day, day, limit=15)
        return {"in": rep["in"]["total"], "out": rep["out"]["total"],
                "rows": [{"time": r["created_at"][11:16], "id": r["id"], "vno": r["vno"], "net": r["net_kg"]}
                         for r in rows]}

    def _handler(self):
        lv, svc = self, self.svc

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                pass

            def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not lv._auth_ok(self.headers.get("Authorization"), self.client_address[0]):
                    return self._send(401, b"Password needed", "text/plain",
                                      {"WWW-Authenticate": 'Basic realm="ISWM live view (user: viewer)"'})
                path = self.path.split("?")[0]
                if path in ("/", "/index.html"):
                    cams = "\n".join('<div class="cam"><img src="cam/%s.mjpg" alt="%s" onerror="retry(this)"><b>%s</b></div>'
                                      % (n, html.escape(svc.cams.label(n)), html.escape(svc.cams.label(n)))
                                      for n in svc.cams.ordered())
                    page = PAGE % {"site": html.escape(svc.settings.get("site_name") or ""), "cams": cams,
                                   "agency": html.escape(svc.settings.get("agency_name") or "")}
                    return self._send(200, page.encode())
                if path == "/api/live":
                    return self._send(200, json.dumps(svc.wb.live()).encode(), "application/json")
                if path == "/api/today":
                    return self._send(200, json.dumps(lv.today(), default=str).encode(), "application/json")
                if path.startswith("/cam/"):
                    cam = svc.cams.cams.get(path[5:].split(".")[0])
                    if cam is None:
                        return self._send(404, b"", "text/plain")
                    with lv._lock:
                        if lv.streams >= MAX_STREAMS:
                            return self._send(503, b"Too many viewers", "text/plain")
                        lv.streams += 1
                    try:
                        stream_mjpeg(self, cam, interval=0.15, demand=True)  # ~6 frames a second is plenty for watching
                    finally:
                        with lv._lock:
                            lv.streams -= 1
                    return
                self._send(404, b"Not found", "text/plain")

        return H


def lan_addresses():
    """This PC's network addresses, to show the admin what to type on the other computer."""
    import socket
    out = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            out.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        out.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(a for a in out if not a.startswith("127."))


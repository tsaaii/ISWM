"""ISWM shared API: read-only, real-time access to every site's records in Firestore.

Runs on Google Cloud Run (scales to zero: no cost while nobody calls it).

Auth: each consumer gets an API key, sent as header  X-API-Key: <key>.
Keys come from the API_KEYS environment variable:
    API_KEYS="cityoffice:k3y1,dashboard:k3y2@iswm-donthali|iswm-kadiri"
A key with @sites can only see those sites.

Endpoints (all JSON):
    GET /v1/sites
    GET /v1/sites/<site>/entries?from=YYYY-MM-DD&to=YYYY-MM-DD&dir=in|out&vehicle=AP39..&limit=500
    GET /v1/sites/<site>/summary?date=YYYY-MM-DD
    GET /v1/sites/<site>/vehicles
    GET /v1/sites/<site>/stream          live: Server-Sent Events, one event per new/changed trip

Remote camera view (relay), see the "Remote camera view" part below:
    GET /live/<site>?key=<api key>       viewer page: cameras + live weight, from anywhere
"""
import datetime as dt
import json
import os
import queue
import re
import secrets
import threading
import time

from flask import Flask, Response, abort, jsonify, request

app = Flask(__name__)
_db = None
TZ = dt.timezone(dt.timedelta(minutes=int(os.environ.get("SITE_UTC_OFFSET_MINUTES", "330"))))  # India by default


def db():
    global _db
    if _db is None:
        from google.cloud import firestore
        _db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "(default)"))
    return _db


def keys():
    out = {}
    for item in filter(None, (os.environ.get("API_KEYS") or "").split(",")):
        name, _, rest = item.strip().partition(":")
        key, _, sites = rest.partition("@")
        out[key] = (name, set(filter(None, sites.split("|"))))
    return out


def allowed_sites():
    got = request.headers.get("X-API-Key") or request.args.get("key") or ""
    for key, (name, sites) in keys().items():
        if secrets.compare_digest(got, key):
            return sites  # empty set = every site
    abort(401, "Send a valid X-API-Key header.")


def check_site(site):
    sites = allowed_sites()
    if not re.fullmatch(r"[a-z0-9-]{1,60}", site) or (sites and site not in sites):
        abort(404, "No such site for this key.")


def clean(d):
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        out[k] = v
    return out


def day_range(a, b):
    start = dt.datetime.combine(dt.date.fromisoformat(a), dt.time(), TZ)
    end = dt.datetime.combine(dt.date.fromisoformat(b), dt.time(), TZ) + dt.timedelta(days=1)
    return start, end


@app.get("/v1/sites")
def sites():
    mine = allowed_sites()
    out = [dict(clean(s.to_dict() or {}), id=s.id) for s in db().collection("sites").stream()]
    return jsonify([s for s in out if not mine or s["id"] in mine])


@app.get("/v1/sites/<site>/entries")
def entries(site):
    check_site(site)
    today = dt.datetime.now(TZ).date().isoformat()
    start, end = day_range(request.args.get("from", today), request.args.get("to", request.args.get("from", today)))
    q = (db().collection("sites").document(site).collection("entries")
         .where("created_at", ">=", start).where("created_at", "<", end).order_by("created_at", direction="DESCENDING"))
    rows = [clean(d.to_dict()) for d in q.limit(min(5000, int(request.args.get("limit", 500)))).stream()]
    if request.args.get("dir") in ("in", "out"):
        rows = [r for r in rows if r.get("dir") == request.args["dir"]]
    v = re.sub(r"[^A-Z0-9]", "", request.args.get("vehicle", "").upper())
    if v:
        rows = [r for r in rows if v in re.sub(r"[^A-Z0-9]", "", str(r.get("vno", "")))]
    return jsonify(rows)


@app.get("/v1/sites/<site>/summary")
def summary(site):
    check_site(site)
    day = request.args.get("date", dt.datetime.now(TZ).date().isoformat())
    start, end = day_range(day, day)
    q = (db().collection("sites").document(site).collection("entries")
         .where("created_at", ">=", start).where("created_at", "<", end))
    out = {"date": day, "in": {}, "out": {}, "incomplete": 0}
    for d in q.stream():
        r = d.to_dict()
        if r.get("net_kg") is None:
            out["incomplete"] += 1
            continue
        key = r.get("waste_type") if r.get("dir") == "in" else r.get("material")
        b = out[r.get("dir", "in")].setdefault(key or "Other", {"trips": 0, "net_kg": 0})
        b["trips"] += 1
        b["net_kg"] += r["net_kg"]
    return jsonify(out)


@app.get("/v1/sites/<site>/vehicles")
def vehicles(site):
    check_site(site)
    return jsonify([clean(d.to_dict()) for d in db().collection("sites").document(site).collection("vehicles").stream()])


@app.get("/v1/sites/<site>/stream")
def stream(site):
    """Real time: every new or changed trip at this site, as it reaches the cloud."""
    check_site(site)
    events = queue.Queue()
    since = dt.datetime.now(TZ) - dt.timedelta(minutes=int(request.args.get("minutes", 60)))
    q = db().collection("sites").document(site).collection("entries").where("synced_at", ">=", since)

    def on_change(snapshot, changes, read_time):
        for c in changes:
            if c.type.name in ("ADDED", "MODIFIED"):
                events.put(clean(c.document.to_dict()))

    watch = q.on_snapshot(on_change)

    def gen():
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    yield "data: %s\n\n" % json.dumps(events.get(timeout=25), default=str)
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            watch.unsubscribe()

    return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# --- Remote camera view (relay) -------------------------------------------------------
# The plant PC is behind the plant's router, so nobody can connect to it from outside.
# Instead it asks this relay every ~20 seconds "is anyone watching?" (a tiny request).
# Only while a viewer has the page open does the plant send small JPEG pictures here,
# and the relay passes them on to the viewer. No viewer = no pictures sent = no data used.
#
# State is kept in memory, so deploy this service with --max-instances 1.
# Plant keys: PLANT_KEYS="iswm-donthali:SECRET1,iswm-kadiri:SECRET2" (one per site).

LIVE = {}
LIVE_LOCK = threading.Lock()
VIEW_MINUTES = int(os.environ.get("LIVE_MAX_MINUTES", "10"))  # a viewing session pauses after this, to save data
QUALITY = {"low": (480, 50, 1.0), "normal": (640, 60, 1.0), "high": (960, 70, 2.0)}  # width, jpeg quality, fps


def live(site):
    with LIVE_LOCK:
        return LIVE.setdefault(site, {"want": {}, "frames": {}, "weight": None, "seen": 0.0, "q": "normal",
                                      "cond": threading.Condition(), "bytes": 0,
                                      "cams": [["front", "Front camera"], ["back", "Back camera"]]})


CAM_NAME = re.compile(r"front|back|cam[3-9]")


def take_cam_names(st):
    """The plant sends its camera list with the names the admin gave them (Front cam, Tipping floor, ...)."""
    try:
        cams = json.loads(request.headers.get("X-Cams") or "null")
    except ValueError:
        return
    if isinstance(cams, list):
        got = [[str(c[0]), str(c[1]).strip()[:24] or str(c[0])] for c in cams[:8]
               if isinstance(c, list) and len(c) == 2 and CAM_NAME.fullmatch(str(c[0]))]
        if got:
            st["cams"] = got


def cam_ok(cam):
    if not CAM_NAME.fullmatch(cam or ""):
        abort(404, "No such camera.")


def plant_ok(site):
    want = dict(p.split(":", 1) for p in filter(None, (os.environ.get("PLANT_KEYS") or "").split(",")))
    got = request.headers.get("X-Site-Key") or ""
    if site not in want or not secrets.compare_digest(got, want[site]):
        abort(401, "Wrong site key.")


def wanted(st):
    now = time.time()
    return sorted(c for c, until in st["want"].items() if until > now)


@app.get("/v1/plant/<site>/wanted")
def plant_wanted(site):
    """The plant asks: is anyone watching? Answers in a few bytes."""
    plant_ok(site)
    st = live(site)
    st["seen"] = time.time()
    take_cam_names(st)
    try:  # the plant's health for the dashboard: weighbridge, cameras, records waiting to sync, version
        status = json.loads(request.headers.get("X-Status") or "null")
        if isinstance(status, dict) and len(json.dumps(status)) < 2000:
            st["status"] = status
    except ValueError:
        pass
    w, q, f = QUALITY[st["q"]]
    return jsonify({"cams": wanted(st), "width": w, "quality": q, "fps": f})


@app.get("/v1/live/status")
def live_status_all():
    """Every plant that has checked in with the relay since it started: online (checked in within a minute),
    seconds since last check-in, and its health. One call for a whole status board; no Firestore reads."""
    mine = allowed_sites()
    now = time.time()
    with LIVE_LOCK:
        items = list(LIVE.items())
    return jsonify({site: {"online": now - st["seen"] < 60, "seen_s": round(now - st["seen"]) if st["seen"] else None,
                           "status": st.get("status"), "cams": st["cams"]}
                    for site, st in items if st["seen"] and (not mine or site in mine)})


@app.post("/v1/plant/<site>/frame/<cam>")
def plant_frame(site, cam):
    """The plant sends one picture (only while someone watches). Replies with who is still watching."""
    plant_ok(site)
    cam_ok(cam)
    data = request.get_data(cache=False)
    if not data.startswith(b"\xff\xd8") or len(data) > 2_000_000:
        abort(400, "Send a JPEG.")
    st = live(site)
    st["seen"] = time.time()
    take_cam_names(st)
    try:
        st["weight"] = json.loads(request.headers.get("X-Weight") or "null")
    except ValueError:
        pass
    with st["cond"]:
        st["frames"][cam] = (data, time.time())
        st["bytes"] += len(data)
        st["cond"].notify_all()
    w, q, f = QUALITY[st["q"]]
    return jsonify({"cams": wanted(st), "width": w, "quality": q, "fps": f})


@app.get("/v1/sites/<site>/live/<cam>.mjpg")
def live_stream(site, cam):
    """A viewer watches one camera. Watching is what makes the plant send pictures."""
    check_site(site)
    cam_ok(cam)
    st = live(site)
    if request.args.get("q") in QUALITY:
        st["q"] = request.args["q"]
    end = time.time() + VIEW_MINUTES * 60

    def gen():
        last = None
        while time.time() < end:
            st["want"][cam] = time.time() + 12
            with st["cond"]:
                st["cond"].wait(timeout=10)
                frame = st["frames"].get(cam)
            if frame and frame is not last and time.time() - frame[1] < 15:
                last = frame
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame[0])).encode() + \
                    b"\r\n\r\n" + frame[0] + b"\r\n"
        st["want"].pop(cam, None)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/v1/sites/<site>/live/state")
def live_state(site):
    check_site(site)
    st = live(site)
    now = time.time()
    return jsonify({"plant_online": now - st["seen"] < 60, "weight": st["weight"], "watching": wanted(st),
                    "frame_age": {c: round(now - f[1], 1) for c, f in st["frames"].items()},
                    "mb_sent": round(st["bytes"] / 1e6, 1), "max_minutes": VIEW_MINUTES, "quality": st["q"],
                    "cams": st["cams"], "status": st.get("status")})


@app.get("/live/<site>")
def live_page(site):
    check_site(site)
    return Response(LIVE_PAGE.replace("{{SITE}}", site), mimetype="text/html")


LIVE_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{{SITE}} · remote view</title>
<style>
body{margin:0;background:#F2FBF4;color:#121A14;font-family:"Palatino Linotype",Palatino,Georgia,serif}
header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 16px;background:#fff;border-bottom:4px solid #1B8A3A}
h1{font-size:20px;margin:0}.pill{padding:4px 12px;border-radius:999px;font-weight:700;color:#fff;background:#9AA79F}
button{font:inherit;font-weight:700;height:38px;padding:0 14px;border-radius:999px;border:2px solid #9AA79F;background:#fff;cursor:pointer}
button.on{background:#0E5230;border-color:#0E5230;color:#fff}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;padding:12px 16px}
.cam{position:relative;border-radius:14px;overflow:hidden;background:#C9CFCB;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:#33413A;font-weight:700}
.cam img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000}
.cam b{position:absolute;left:10px;top:10px;padding:3px 10px;border-radius:999px;background:rgba(18,26,20,.6);color:#fff;font-size:13px;z-index:1}
#w{font-size:28px;font-variant-numeric:tabular-nums}.muted{color:#33413A;font-size:14px}
</style></head><body>
<header><h1>{{SITE}}</h1><span id="plant" class="pill">…</span><span><span id="w">—</span> kg</span>
<span style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap">
<span id="pick" style="display:contents"></span>
<button data-q="low">Low data</button><button data-q="normal" class="on">Normal</button><button data-q="high">Sharper</button>
<button id="stop">Stop</button></span></header>
<main id="cams"></main>
<p class="muted" style="padding:0 16px" id="info">Pictures are sent only while this page is open, and pause after a few minutes to save data.</p>
<script>
var key=new URLSearchParams(location.search).get('key')||'', site='{{SITE}}', cams=['front'], q='normal', on=true, list=null, names={};
function api(p){return fetch('/v1/sites/'+site+p,{headers:{'X-API-Key':key}}).then(function(r){return r.json()})}
function draw(){var m=document.getElementById('cams');m.innerHTML='';if(!on){m.innerHTML='<div class="cam">Stopped. Choose a camera to watch again.</div>';return}
 cams.forEach(function(c){var d=document.createElement('div');d.className='cam';d.innerHTML='<b></b><span>Waiting for the plant… (up to 20 s)</span>';var bb=d.querySelector('b');bb.dataset.c=c;bb.textContent=names[c]||c;
 var i=new Image();i.onload=function(){var sp=d.querySelector('span');if(sp)sp.remove()};
 i.onerror=function(){setTimeout(draw,5000)};i.src='/v1/sites/'+site+'/live/'+c+'.mjpg?key='+encodeURIComponent(key)+'&q='+q+'&t='+Date.now();d.appendChild(i);m.appendChild(d)})}
function buttons(l){var k=JSON.stringify(l);if(k===list)return;list=k;var p=document.getElementById('pick');p.innerHTML='';
 l.forEach(function(c){names[c[0]]=c[1]});
 // the plant renamed or removed a camera: update the names on screen, and leave a camera that is gone
 document.querySelectorAll('.cam b[data-c]').forEach(function(x){x.textContent=names[x.dataset.c]||x.dataset.c});
 var ids=l.map(function(c){return c[0]}),keep=cams.filter(function(c){return ids.indexOf(c)>=0});
 if(!keep.length&&ids.length){cams=[ids[0]];draw()}else if(keep.length<cams.length){cams=keep;draw()}var opts=l.map(function(c){return [c[0],c[1]]});if(l.length>1)opts.push([l.map(function(c){return c[0]}).join(','),'All']);
 opts.forEach(function(o){var b=document.createElement('button');b.dataset.cams=o[0];b.textContent=o[1];b.className=o[0]===cams.join(',')?'on':'';
 b.onclick=function(){cams=o[0].split(',');on=true;p.querySelectorAll('button').forEach(function(x){x.className=x===b?'on':''});draw()};p.appendChild(b)})}
document.querySelectorAll('[data-q]').forEach(function(b){b.onclick=function(){q=b.dataset.q;
 document.querySelectorAll('[data-q]').forEach(function(x){x.className=x===b?'on':''});draw()}});
document.getElementById('stop').onclick=function(){on=false;draw()};
function tick(){api('/live/state').then(function(s){if(s.cams)buttons(s.cams);var p=document.getElementById('plant');p.textContent=s.plant_online?'Plant online':'Plant offline';
 p.style.background=s.plant_online?'#1B8A3A':'#C62828';var w=s.weight;document.getElementById('w').textContent=w&&w.connected?Math.round(w.weight).toLocaleString('en-IN'):'—';
 document.getElementById('info').textContent='Pictures are sent only while this page is open. Each view pauses after '+s.max_minutes+' minutes. Sent through the relay since it started: '+s.mb_sent+' MB.'}).catch(function(){})}
draw();tick();setInterval(tick,3000);
</script></body></html>"""


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
def err(e):
    return jsonify({"error": e.description}), e.code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

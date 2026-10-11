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
"""
import datetime as dt
import json
import os
import queue
import re
import secrets

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


@app.errorhandler(401)
@app.errorhandler(404)
def err(e):
    return jsonify({"error": e.description}), e.code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

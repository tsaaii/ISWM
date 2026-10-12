"""Send records to Google Cloud Firestore, using as little internet as possible.

Why Firestore: no server to run or pay for while idle, a free daily quota
(20,000 writes, 50,000 reads) that covers a plant's few hundred trips, and
real-time updates built in for the shared API (see cloud_api/).

Layout (one tree per site, so many sites share one project):
  sites/{site_id}                      name, company, last sync, app version
  sites/{site_id}/entries/{ticket}     every inward / outward trip
  sites/{site_id}/tares/{id}           empty weights
  sites/{site_id}/vehicles/{vkey}      vehicle number and its empty weight
  sites/{site_id}/batches|samples|corrections/{id}
A site can instead use its own Firestore database (setting "database").

Data saving rules:
  * nothing is sent while there is nothing new: no polling, no keep-alive;
  * new records are collected locally and sent together, every
    ``sync_minutes`` (default 10), in one HTTPS request (up to 400 records);
  * when the internet is down, the wait doubles up to an hour;
  * photos are not uploaded unless the admin chooses "small" (~100 KB) or "full".
The local database stays the source of truth; nothing is lost while offline.
"""
import json
import logging
import os
import re
import threading
import time
import urllib.parse

FS = "https://firestore.googleapis.com/v1/"
GCS_UPLOAD = "https://storage.googleapis.com/upload/storage/v1/b/%s/o?uploadType=media&name=%s"
SCOPES = ["https://www.googleapis.com/auth/datastore", "https://www.googleapis.com/auth/devstorage.read_write"]
COLLECTION = {"entry": "entries", "tare": "tares", "batch": "batches", "sample": "samples", "correction": "corrections"}
MAX_WRITES = 400
_tz = time.strftime("%z") or "+0000"
TZ = _tz[:3] + ":" + _tz[3:]
SKIP_FIELDS = {"front_photo", "back_photo", "extra_photos", "vkey"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "site"


def fs_value(v):
    """Python value -> Firestore REST value."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"integerValue": str(int(v))} if v.is_integer() else {"doubleValue": v}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [fs_value(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {str(k): fs_value(x) for k, x in v.items()}}}
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", v):
        # local plant time, stored as a real timestamp with this PC's time zone
        return {"timestampValue": v.replace(" ", "T") + TZ}
    return {"stringValue": str(v)}


def fs_fields(rec):
    return {k: fs_value(v) for k, v in rec.items() if k not in SKIP_FIELDS}


def small_jpeg(path, width=1280, quality=70):
    """A smaller copy of a photo for upload (about 100 KB instead of 0.5 MB)."""
    import cv2
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


class CloudSync:
    def __init__(self, database, settings):
        self.db = database
        self.settings = settings
        self.state = "off"  # synced | offline | error | off
        self.message = None
        self.last_sent = None
        self.next_at = None
        self.bytes_sent = 0
        self._session = None
        self._session_key = None
        self._backoff = 1
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._run_lock = threading.Lock()

    # lifecycle ---------------------------------------------------------------
    def start(self):
        self._stop.clear()
        threading.Thread(target=self._loop, daemon=True, name="cloud-sync").start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def kick(self):
        """A record was saved. It is sent at the next scheduled send, not now (saves data)."""
        cfg = self.cfg()
        if cfg.get("enabled") and int(cfg.get("sync_minutes") or 10) == 0:
            self._wake.set()  # "send right away" was chosen

    def retry_now(self):
        self.run_once()
        return self.state

    def cfg(self):
        return self.settings.get("cloud") or {}

    def site_id(self):
        return self.cfg().get("site_id") or slug(self.settings.get("site_name"))

    def _loop(self):
        self._stop.wait(5)
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as e:
                self.state, self.message = "error", str(e)[:200]
            minutes = int(self.cfg().get("sync_minutes") or 10) or 10
            wait = min(3600, minutes * 60 * self._backoff)
            self.next_at = time.time() + wait
            self._wake.wait(wait)
            self._wake.clear()

    # sending ---------------------------------------------------------------
    def _auth(self, cfg):
        key = (cfg.get("credentials_path"),)
        if self._session is None or self._session_key != key:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
            creds = service_account.Credentials.from_service_account_file(cfg["credentials_path"], scopes=SCOPES)
            self._session, self._session_key = AuthorizedSession(creds), key
            self._project = cfg.get("project_id") or creds.project_id
        return self._session

    def run_once(self):
        with self._run_lock:
            self._run_once()

    def _run_once(self):
        cfg = self.cfg()
        if not cfg.get("enabled") or not cfg.get("credentials_path"):
            self.state, self.message = "off", "Sync is not set up. Ask the admin."
            return
        waiting = self.db.queue_waiting()
        if not waiting:  # nothing new: no internet used at all
            if self.state != "error":
                self.state = "synced"
            return
        try:
            session = self._auth(cfg)
        except Exception as e:
            self.state, self.message = "error", "Key file problem: " + str(e)[:160]
            return
        site = self.site_id()
        dbname = cfg.get("database") or "(default)"
        base = "projects/%s/databases/%s/documents/" % (self._project, dbname)
        photos = cfg.get("photos") or "off"
        # newest version of each record once, even if it was queued several times
        latest, done_ids = {}, []
        for item in waiting:
            latest[(item["kind"], item["ref"])] = item
            done_ids.append(item["id"])
        writes, vehicles = [], set()
        for (kind, ref), item in list(latest.items())[:MAX_WRITES]:
            rec = self.db.payload(kind, ref)
            if rec is None:
                continue
            rec = dict(rec)
            if photos != "off":
                for field in ("front_photo", "back_photo"):
                    p = rec.get(field)
                    if p and os.path.exists(p) and cfg.get("bucket_name"):
                        rec[field.replace("_photo", "_image")] = self._upload_photo(session, cfg, site, p, photos)
            rec["site"] = site
            rec["synced_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            writes.append({"update": {"name": base + "sites/%s/%s/%s" % (site, COLLECTION.get(kind, "other"),
                                                                            urllib.parse.quote(str(ref), safe="")),
                                      "fields": fs_fields(rec)}})
            if rec.get("vno"):
                vehicles.add(rec["vno"])
        for vno in vehicles:
            v = self.db.vehicle(vno)
            if v:
                writes.append({"update": {"name": base + "sites/%s/vehicles/%s" % (site, v["vkey"]),
                                          "fields": fs_fields({"vno": v["vno"], "tare_kg": v["tare_kg"],
                                                              "tare_at": v["tare_at"], "site": site})}})
        writes.append({"update": {"name": base + "sites/%s" % site,
                                  "fields": fs_fields({"name": self.settings.get("site_name"),
                                                       "company": self.settings.get("agency_name"),
                                                       "cameras": self.camera_names(),
                                                       "last_sync": time.strftime("%Y-%m-%d %H:%M:%S")})}})
        body = json.dumps({"writes": writes}, default=str)
        try:
            r = session.post(FS + base.rstrip("/") + ":commit", data=body,
                             headers={"Content-Type": "application/json"}, timeout=30)
        except Exception as e:  # no internet: try again later, waiting longer each time
            self._backoff = min(6, self._backoff * 2)
            self.state, self.message = "offline", str(e)[:160]
            return
        self.bytes_sent += len(body)
        if r.status_code != 200:
            self.state, self.message = "error", "Server said %d: %s" % (r.status_code, r.text[:160])
            for qid in done_ids:
                self.db.queue_failed(qid, self.message)
            return
        sent = {(k, f) for (k, f) in list(latest.keys())[:MAX_WRITES]}
        for item in waiting:
            if (item["kind"], item["ref"]) in sent:
                self.db.queue_done(item["id"])
        self._backoff = 1
        self.last_sent = time.strftime("%H:%M")
        self.state, self.message = ("synced", None) if len(latest) <= MAX_WRITES else ("offline", "More to send")
        logging.info("sync: sent %d records, %d bytes", len(writes), len(body))

    def camera_names(self):
        """[{id, name}] in screen order, e.g. {"id": "cam3", "name": "Tipping floor"}."""
        from .settings import camera_ids
        cams = self.settings.get("cameras") or {}
        return [{"id": k, "name": cams[k].get("label") or k} for k in camera_ids(cams)]

    def _upload_photo(self, session, cfg, site, path, mode):
        data = small_jpeg(path) if mode == "small" else open(path, "rb").read()
        if not data:
            return None
        day = os.path.basename(os.path.dirname(path))
        name = "%s/%s/%s" % (site, day, os.path.basename(path))
        try:
            r = session.post(GCS_UPLOAD % (cfg["bucket_name"], urllib.parse.quote(name, safe="")), data=data,
                             headers={"Content-Type": "image/jpeg"}, timeout=60)
            self.bytes_sent += len(data)
            return "gs://%s/%s" % (cfg["bucket_name"], name) if r.status_code == 200 else None
        except Exception:
            return None

    def status(self):
        return {"state": self.state, "message": self.message, "lastSent": self.last_sent,
                "nextIn": max(0, int((self.next_at - time.time()) / 60)) if self.next_at else None,
                "bytes": self.bytes_sent, "site": self.site_id()}


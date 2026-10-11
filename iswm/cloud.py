"""Background upload of records and photos to Google Cloud Storage.

Bucket layout follows adex_lite's cloud_storage.get_cloud_path():
``<agency>/<site>/<YYYY-MM-DD>/<folder>/<file>``. Every saved record goes into
the local sync_queue first; this worker drains it. The local database is
always the source of truth, so the plant keeps working with no internet.
"""
import json
import os
import threading


def clean(s):
    return str(s).replace(" ", "_").replace("/", "_").replace("\\", "_").replace(":", "_")


FOLDERS = {"entry": "entries", "tare": "tares", "batch": "batches", "sample": "samples",
           "correction": "corrections"}


class CloudSync:
    def __init__(self, database, settings):
        self.db = database
        self.settings = settings
        self.state = "offline"  # synced | offline | error | off
        self.message = None
        self._bucket = None
        self._bucket_key = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._run_lock = threading.Lock()

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cloud-sync")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def kick(self):
        self._wake.set()

    def _get_bucket(self, cfg):
        key = (cfg.get("bucket_name"), cfg.get("credentials_path"))
        if self._bucket is not None and self._bucket_key == key:
            return self._bucket
        from google.cloud import storage  # imported late: slow, and only needed when sync is on
        creds = cfg.get("credentials_path")
        client = storage.Client.from_service_account_json(creds) if creds else storage.Client()
        self._bucket, self._bucket_key = client.bucket(cfg["bucket_name"]), key
        return self._bucket

    def run_once(self):
        with self._run_lock:
            self._run_once()

    def _run_once(self):
        cfg = self.settings.get("cloud") or {}
        if not cfg.get("enabled") or not cfg.get("bucket_name"):
            self.state, self.message = "off", "Sync is not set up. Ask the admin."
            return
        waiting = self.db.queue_waiting()
        if not waiting:
            self.state, self.message = "synced", None
            return
        try:
            bucket = self._get_bucket(cfg)
        except Exception as e:
            self.state, self.message = "error", str(e)[:200]
            return
        agency, site = clean(self.settings.get("agency_name")), clean(self.settings.get("site_name"))
        for item in waiting:
            if self._stop.is_set():
                return
            try:
                rec = self.db.payload(item["kind"], item["ref"])
                if rec is None:
                    self.db.queue_done(item["id"])
                    continue
                day = (rec.get("created_at") or item["created_at"])[:10]
                base = "%s/%s/%s/" % (agency, site, day)
                for field in ("front_photo", "back_photo"):
                    p = rec.get(field)
                    if p and os.path.exists(p):
                        name = base + "images/" + os.path.basename(p)
                        bucket.blob(name).upload_from_filename(p, content_type="image/jpeg", timeout=60)
                        rec[field + "_cloud"] = name
                name = base + FOLDERS.get(item["kind"], "other") + "/" + clean(item["ref"]) + ".json"
                bucket.blob(name).upload_from_string(json.dumps(rec, indent=2, default=str),
                                                     content_type="application/json", timeout=30)
                self.db.queue_done(item["id"])
            except Exception as e:
                self.db.queue_failed(item["id"], e)
                offline = any(w in str(e).lower() for w in ("connection", "timed out", "resolve", "network",
                                                             "unreachable", "max retries"))
                self.state = "offline" if offline else "error"
                self.message = str(e)[:200]
                return
        self.state, self.message = "synced", None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as e:
                self.state, self.message = "error", str(e)[:200]
            delay = 15 if self.state == "synced" else 30
            self._wake.wait(delay)
            self._wake.clear()

    def retry_now(self):
        self.run_once()
        return self.state


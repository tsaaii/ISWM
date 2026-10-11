"""Daily housekeeping: database backup, and removing old files so the disk never fills.

What is kept and for how long is set by the admin (settings "retention"):
  * photos: images/<date>/ folders older than photos_days are removed, but
    never a day that still has records waiting to upload;
  * reports (CSV downloads), logs: removed after reports_days / logs_days;
  * database backups: one per day in backups/, kept backups_days.
The database itself (every record, every ticket) is never trimmed.
"""
import datetime as dt
import logging
import os
import shutil
import threading
import time

from . import paths


def _days_old(name_or_mtime, today):
    if isinstance(name_or_mtime, (int, float)):
        return (time.time() - name_or_mtime) / 86400
    try:
        return (today - dt.date.fromisoformat(name_or_mtime)).days
    except ValueError:
        return None


def folder_size(path):
    total, files = 0, 0
    for root, _, names in os.walk(path):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(root, n))
                files += 1
            except OSError:
                pass
    return total, files


class Maintenance:
    def __init__(self, service):
        self.svc = service
        self.last_run = None
        self.last_report = {}
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="maintenance").start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        self._stop.wait(20)  # let the app start first
        while not self._stop.is_set():
            try:
                self.run()
            except Exception:
                logging.exception("maintenance failed")
            self._stop.wait(6 * 3600)

    def run(self):
        ret = self.svc.settings.get("retention") or {}
        today = dt.date.today()
        report = {"removed_photo_days": 0, "removed_files": 0}
        # 1. backup the database once a day
        bdir = paths.sub("backups")
        target = os.path.join(bdir, "iswm-%s.sqlite3" % today.isoformat())
        if not os.path.exists(target):
            self.svc.db.backup_to(target)
            report["backup"] = target
        # 2. old photos, but never a day with records still waiting to upload
        keep = int(ret.get("photos_days") or 0)
        waiting = self.svc.db.queue_waiting()
        oldest_waiting = min((w["created_at"][:10] for w in waiting), default=None)
        img = paths.sub("images")
        if keep > 0:
            for name in os.listdir(img):
                age = _days_old(name, today)
                if age is None or age <= keep or (oldest_waiting and name >= oldest_waiting):
                    continue
                shutil.rmtree(os.path.join(img, name), ignore_errors=True)
                report["removed_photo_days"] += 1
        # 3. reports, logs, backups by file age
        for folder, days in ((self.svc.reports_folder(), ret.get("reports_days")),
                             (paths.sub("logs"), ret.get("logs_days")),
                             (bdir, ret.get("backups_days"))):
            days = int(days or 0)
            if days <= 0:
                continue
            for n in os.listdir(folder):
                f = os.path.join(folder, n)
                if os.path.isfile(f) and n not in ("iswm.log", "console.log"):  # the files in use stay
                    try:
                        if _days_old(os.path.getmtime(f), today) > days:
                            os.remove(f)
                            report["removed_files"] += 1
                    except OSError:
                        pass
        self.last_run, self.last_report = time.strftime("%Y-%m-%d %H:%M"), report
        logging.info("maintenance: %s", report)
        return report

    def storage(self):
        """Sizes for the admin screen."""
        out = {}
        for key, folder in (("photos", paths.sub("images")), ("reports", self.svc.reports_folder()),
                            ("backups", paths.sub("backups")), ("logs", paths.sub("logs"))):
            size, files = folder_size(folder)
            out[key] = {"mb": round(size / 1e6, 1), "files": files}
        try:
            out["database_mb"] = round(os.path.getsize(self.svc.db.path) / 1e6, 1)
        except OSError:
            out["database_mb"] = 0
        du = shutil.disk_usage(paths.data_dir())
        out["disk_free_gb"] = round(du.free / 1e9, 1)
        out["disk_total_gb"] = round(du.total / 1e9, 1)
        out["last_run"] = self.last_run
        return out

"""Everything the screens can ask for. One method per UI action.

Methods take and return plain JSON-able values. ``RuleError`` messages are
shown to the operator as-is, so they are written in the app's plain voice.
"""
import base64
import binascii
import csv
import datetime as dt
import os
import random
import subprocess
import sys
import time

from . import __version__, paths
from .cameras import Cameras
from .cloud import CloudSync
from .db import DB, MATERIALS, RECYC, IN_TYPES, RuleError, norm_vno, yymm
from .settings import (BRANDS, Settings, check_pin, hash_password, hash_pin, password_problem,
                       pin_problem)
from .liveview import LiveView, lan_addresses
from .maintenance import Maintenance
from .weighbridge import Weighbridge, list_ports

ADMIN_TTL_S = 15 * 60


def rnd(a, b):
    return round((a + random.random() * (b - a)) / 10) * 10


def cell(v):
    """Stop free text (e.g. a destination) being run as an Excel formula."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def parse_day(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


class Service:
    def __init__(self, settings=None, database=None, start_devices=True):
        self.db = database or DB()
        self.settings = settings or Settings(store=self.db)
        self.db_ok = self.db.integrity_ok()
        self.wb = Weighbridge(self.settings.get("weighbridge"))
        self.cams = Cameras(self.settings.get("cameras"))
        self.cloud = CloudSync(self.db, self.settings)
        self.operator = None
        self._admin_until = 0.0
        self._fails = {}
        self.window = None  # set by main.py when running in a pywebview window
        self._full = False
        self.maint = Maintenance(self)
        self.liveview = LiveView(self)
        if start_devices:
            self.wb.start()
            self.cams.start()
            self.cloud.start()
            self.maint.start()
            self.liveview.apply()

    def shutdown(self):
        self.liveview.stop()
        self.maint.stop()
        self.wb.stop()
        self.cams.stop()
        self.cloud.stop()

    # sign-in -------------------------------------------------------------
    def boot(self):
        return {"site": self.settings.get("site_name"), "agency": self.settings.get("agency_name"),
                "operators": self.settings.operator_names(), "needsSetup": not self.settings.get("admin_password_hash"),
                "logo": self.logo_version(), "admin": self.admin_active(),
                "version": __version__, "operator": self.operator, "inWindow": self.window is not None}

    def _throttle(self, key):
        n, until = self._fails.get(key, (0, 0.0))
        if time.monotonic() < until:
            raise RuleError("Too many wrong tries. Wait %d seconds." % int(until - time.monotonic() + 1))

    def _failed(self, key):
        n, _ = self._fails.get(key, (0, 0.0))
        n += 1
        self._fails[key] = (n, time.monotonic() + (60 if n >= 5 else 0))

    def login(self, name, pin):
        self._throttle("op:" + str(name))
        if not self.settings.check_operator(name, pin):
            self._failed("op:" + str(name))
            raise RuleError("Wrong PIN. Try again.")
        self._fails.pop("op:" + str(name), None)
        self.operator = name
        return {"operator": name}

    def logout(self):
        self.operator = None
        return {}

    def _op(self):
        if not self.operator:
            raise RuleError("Sign in first.")
        return self.operator

    # live ------------------------------------------------------------------
    def live(self):
        queued = len(self.db.queue_waiting())
        return {"admin": self.admin_active(), "wb": self.wb.live(), "simulate": bool(self.settings.get("weighbridge").get("simulate")),
                "minKg": float(self.settings.get("weighbridge").get("min_weight_kg") or 10),
                "sync": {"state": self.cloud.state, "queued": queued, "message": self.cloud.message},
                "cams": self.cams.status()}

    def state(self):
        vehicles = self.db.vehicle_list()
        today = self.db.today_entries()
        q = self.db.queue_waiting()
        trips = self.db.unprocessed_trips()
        return {
            "vehicles": [{"vno": v["vno"], "tare": v["tare_kg"]} for v in vehicles],
            "pending": [{"vno": p["vno"], "id": p["id"], "gross": p["gross_kg"], "time": p["created_at"][11:16]}
                        for p in self.db.pending()],
            "nextIn": self.db.counter("in"), "nextOut": self.db.counter("out"), "yymm": yymm(),
            "dests": self.db.destinations(self.settings.get("outward_destinations") or []),
            "today": [{"id": e["id"], "dir": e["dir"], "net": e["net_kg"], "asked": e["asked"] > 0,
                       "what": (e["waste_type"] if e["dir"] == "in" else e["material"]) + " · " + e["vno"] +
                               (" · manual" if e["manual"] else "")} for e in today],
            "queue": [{"id": i["ref"], "what": i["label"], "time": i["created_at"][11:16],
                       "failed": bool(i["last_error"])} for i in q],
            "trips": [{"id": t["id"], "vno": t["vno"], "type": t["waste_type"], "net": t["net_kg"],
                       "day": t["created_at"][:10], "time": t["created_at"][11:16]} for t in trips],
            "sampleDue": self.db.sample_due(), "month": dt.date.today().strftime("%B"),
            "shifts": self.settings.get("shifts"),
            "materials": MATERIALS, "inTypes": IN_TYPES, "recyc": RECYC,
        }

    # weighing --------------------------------------------------------------
    def vehicle_status(self, flow, vno):
        return {"status": self.db.vehicle_status(flow, norm_vno(vno))}

    def vehicle_picked(self, flow, vno):
        """Called when the operator picks a vehicle. In simulator mode a load drives onto the bridge."""
        vno = norm_vno(vno)
        st = self.db.vehicle_status(flow, vno)
        if self.settings.get("weighbridge").get("simulate"):
            can = (st in ("known", "new")) if flow == "in" else (st == "known") if flow == "out" else \
                (st in ("pending", "new"))
            v = self.db.vehicle(vno)
            tare = v["tare_kg"] if v and v["tare_kg"] is not None else None
            if not can:
                target = 0
            elif flow == "in":
                target = tare + rnd(2000, 4800) if tare else rnd(4000, 7500)
            elif flow == "out":
                target = (tare or 3000) + rnd(1200, 3800)
            else:
                p = next((x for x in self.db.pending() if x["vno"] == vno), None)
                target = max(900, p["gross_kg"] - rnd(2200, 4200)) if p else rnd(1200, 6000)
            self.wb.sim_load(target)
        return {"status": st}

    def vehicle_cleared(self):
        if self.settings.get("weighbridge").get("simulate"):
            self.wb.sim_load(0)
        return {}

    def _weight(self):
        w = self.wb.capture()
        if w is None:
            raise RuleError("Weight is not steady above %d kg yet." %
                            int(self.settings.get("weighbridge").get("min_weight_kg") or 10))
        return w

    def _photos(self, table, id_, frames, vno, what):
        folder = paths.sub("images", time.strftime("%Y-%m-%d"))
        lines = ["%s - %s" % (self.settings.get("site_name"), vno),
                 time.strftime("%d-%m-%Y %H:%M:%S") + " - " + what]
        photos = self.cams.write(frames, folder, id_, lines, id_)
        self.db.set_photos(table, id_, photos)
        return sum(1 for p in photos if p)

    def save_in(self, vno, source, type):
        op, gross = self._op(), self._weight()
        frames = self.cams.grab()
        with self.db.lock:  # photos are on the record before the uploader can see it
            e = self.db.save_inward(vno, source, type, gross, op)
            n = self._photos("entries", e["id"], frames, e["vno"], "Inward " + source + " " + type)
        self.vehicle_cleared()
        self.cloud.kick()
        return {"entry": e, "photos": n}

    def save_out(self, vno, material, dest, manualKg=None, reason=None):
        op = self._op()
        manual = manualKg not in (None, "")
        gross = None if manual else self._weight()
        frames = {} if manual else self.cams.grab()
        with self.db.lock:
            e = self.db.save_outward(vno, material, dest, gross, op,
                                     manual_kg=float(manualKg) if manual else None, reason=reason)
            n = 0 if manual else self._photos("entries", e["id"], frames, e["vno"], "Outward " + material)
        self.vehicle_cleared()
        self.cloud.kick()
        return {"entry": e, "photos": n}

    def save_tare(self, vno):
        op, w = self._op(), self._weight()
        frames = self.cams.grab()
        with self.db.lock:
            r = self.db.save_tare(vno, w, op)
            n = self._photos("tares", r["tare"]["id"], frames, r["tare"]["vno"], "Empty weight")
        self.vehicle_cleared()
        self.cloud.kick()
        return {**r, "photos": n}

    # recovery, sample, corrections ----------------------------------------
    def save_batch(self, date, ids, outputs):
        r = self.db.save_batch(date, ids, outputs, self._op())
        self.cloud.kick()
        return r

    def save_sample(self, kg, wet, dry, inert):
        f = lambda x: float(x or 0)
        self.db.save_sample(f(kg), f(wet), f(dry), f(inert), self._op())
        self.cloud.kick()
        return {}

    def ask_correction(self, id, reason):
        self.db.ask_correction(id, reason, self._op())
        self.cloud.kick()
        return {}

    def retry_sync(self):
        return {"state": self.cloud.retry_now(), "message": self.cloud.message,
                "queued": len(self.db.queue_waiting())}

    # reports -----------------------------------------------------------------
    def set_shifts(self, count, starts):
        count = 2 if int(count) == 2 else 3
        starts = [s for s in starts if isinstance(s, str) and len(s) == 5][:3]
        while len(starts) < 3:
            starts.append(["06:00", "14:00", "22:00"][len(starts)])
        self.settings.replace("shifts", {"count": count, "starts": starts})
        return self.settings.get("shifts")

    @staticmethod
    def _trip_row(r):
        return {"id": r["id"], "dir": r["dir"], "vno": r["vno"], "day": r["created_at"][:10],
                "time": r["created_at"][11:16], "what": r["waste_type"] if r["dir"] == "in" else r["material"],
                "where": r["source"] if r["dir"] == "in" else r["dest"], "gross": r["gross_kg"], "tare": r["tare_kg"],
                "net": r["net_kg"], "manual": bool(r["manual"]), "operator": r["operator"],
                "asked": r.get("asked"), "edits": r.get("edits", 0), "source": r["source"],
                "waste_type": r["waste_type"], "material": r["material"], "dest": r["dest"]}

    def export_trips(self, dateFrom, dateTo, dir="Both", status="All", q=""):
        rows = self.db.trips(parse_day(dateFrom), parse_day(dateTo), dir, status, q, limit=1000000)
        site = self.settings.get("site_name").replace(" ", "-")
        path = os.path.join(self.reports_folder(), "%s-trips-%s-to-%s.csv" % (site, dateFrom, dateTo))
        cols = [("Date", lambda r: r["created_at"][:10]), ("Time", lambda r: r["created_at"][11:16]),
                ("Ticket", lambda r: r["id"]), ("In/Out", lambda r: "Inward" if r["dir"] == "in" else "Outward"),
                ("Vehicle", lambda r: r["vno"]), ("From / Going to", lambda r: r["source"] or r["dest"]),
                ("Waste / Material", lambda r: r["waste_type"] or r["material"]),
                ("Gross kg", lambda r: r["gross_kg"]), ("Tare kg", lambda r: r["tare_kg"]),
                ("Net kg", lambda r: r["net_kg"]), ("Status", lambda r: "Complete" if r["net_kg"] is not None else "Tare pending"),
                ("Manual", lambda r: "Yes" if r["manual"] else ""), ("Operator", lambda r: r["operator"]),
                ("Fixed by admin", lambda r: "Yes" if r.get("edits") else "")]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cols])
            for r in rows:
                w.writerow([cell(c[1](r)) for c in cols])
        return {"path": path, "folder": os.path.dirname(path)}

    def report(self, view, day=None, period=None, dateFrom=None, dateTo=None, dir="Both", status=None, q=None):
        d = parse_day(day) if day else dt.date.today()
        if view == "daily":
            return self.db.report_daily(d)
        if view == "shift":
            sh = self.settings.get("shifts")
            return {"rows": self.db.report_shift(d, sh["starts"][:sh["count"]]), "shifts": sh}
        if view == "inc":
            return {"rows": [{"id": r["id"], "vno": r["vno"], "gross": r["gross_kg"],
                              "time": r["created_at"][:16]} for r in self.db.report_incomplete()]}
        if view == "trips":
            rows = self.db.trips(parse_day(dateFrom) if dateFrom else d, parse_day(dateTo) if dateTo else d,
                                 dir, status or "All", q or "")
            return {"rows": [self._trip_row(r) for r in rows], "limited": len(rows) >= 2000}
        if view == "custom":
            return {"rows": self.db.report_custom(period, parse_day(dateFrom), parse_day(dateTo), dir)}
        raise RuleError("Unknown report.")

    def reports_folder(self):
        folder = self.settings.get("reports_folder") or os.path.join(paths.data_dir(), "reports")
        os.makedirs(folder, exist_ok=True)
        return folder

    def export_csv(self, period, dateFrom, dateTo, dir="Both"):
        rows = self.db.report_custom(period, parse_day(dateFrom), parse_day(dateTo), dir)
        show_in, show_out = dir != "Outward", dir != "Inward"
        site = self.settings.get("site_name").replace(" ", "-")
        name = "%s-%s-%s-to-%s.csv" % (site, period.lower(), dateFrom, dateTo)
        path = os.path.join(self.reports_folder(), name)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads it as UTF-8
            w = csv.writer(f)
            w.writerow(["Period", "Trips"] + (["Inward net kg"] if show_in else []) +
                       (["Outward net kg"] if show_out else []))
            for r in rows:
                w.writerow([r["label"], r["trips"]] + ([round(r["in_net"])] if show_in else []) +
                           ([round(r["out_net"])] if show_out else []))
        # A full record export alongside, for anyone who needs every trip.
        detail = os.path.join(self.reports_folder(), name.replace(".csv", "-trips.csv"))
        start = dt.datetime.combine(parse_day(dateFrom), dt.time())
        end = dt.datetime.combine(parse_day(dateTo), dt.time()) + dt.timedelta(days=1)
        cols = ["id", "dir", "vno", "source", "waste_type", "material", "dest", "gross_kg", "tare_kg", "net_kg",
                "manual", "manual_reason", "operator", "created_at", "completed_at"]
        with open(detail, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for e in self.db.entries_between(start, end):
                if (dir == "Inward" and e["dir"] != "in") or (dir == "Outward" and e["dir"] != "out"):
                    continue
                w.writerow([cell(e[c]) for c in cols])
        return {"path": path, "detail": detail, "folder": os.path.dirname(path)}

    def open_folder(self, path=None):
        """Open the reports folder (or a folder inside it) in Explorer."""
        base = os.path.realpath(self.reports_folder())
        target = os.path.realpath(path) if path else base
        if target != base and not target.startswith(base + os.sep):
            target = base
        if sys.platform == "win32":
            os.startfile(target)  # noqa: only exists on Windows
        else:
            subprocess.Popen(["xdg-open", target])
        return {}

    # window --------------------------------------------------------------------
    def toggle_full(self, on):
        if self.window is not None and bool(on) != self._full:
            self.window.toggle_fullscreen()
            self._full = bool(on)
        return {"full": self._full}

    # first-run setup -------------------------------------------------------------
    def setup(self, site, agency, adminPassword, operatorName, operatorPin):
        """Only before an admin password exists. Creates the admin password and first operator."""
        if self.settings.get("admin_password_hash"):
            raise RuleError("This computer is already set up.")
        site, agency, name = (site or "").strip(), (agency or "").strip(), (operatorName or "").strip()
        if not site or not name:
            raise RuleError("Type the site name and the first operator's name.")
        problem = pin_problem(operatorPin) or password_problem(adminPassword, [str(operatorPin)])
        if problem:
            raise RuleError(problem)
        self.settings.update({"site_name": site, "agency_name": agency,
                              "admin_password_hash": hash_password(adminPassword)})
        self.settings.replace("operators", [{"name": name, "pin_hash": hash_pin(operatorPin)}])
        return self.boot()

    # branding ----------------------------------------------------------------------
    LOGO_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"RIFF": "webp"}

    def logo_path(self):
        folder = paths.sub("branding")
        for ext in ("png", "jpg", "webp"):
            p = os.path.join(folder, "logo." + ext)
            if os.path.exists(p):
                return p
        return None

    def logo_version(self):
        p = self.logo_path()
        return int(os.path.getmtime(p)) if p else None

    def admin_set_logo(self, dataUrl):
        self._admin()
        try:
            raw = base64.b64decode((dataUrl or "").split(",", 1)[-1], validate=True)
        except (ValueError, binascii.Error):
            raise RuleError("That file is not a picture.")
        ext = next((e for magic, e in self.LOGO_TYPES.items() if raw.startswith(magic)), None)
        if ext is None or (ext == "webp" and raw[8:12] != b"WEBP"):
            raise RuleError("Use a PNG, JPG or WebP picture.")
        if len(raw) > 2 * 1024 * 1024:
            raise RuleError("Logo must be smaller than 2 MB.")
        self.admin_clear_logo()
        with open(os.path.join(paths.sub("branding"), "logo." + ext), "wb") as f:
            f.write(raw)
        return {"logo": self.logo_version()}

    def admin_clear_logo(self):
        self._admin()
        p = self.logo_path()
        while p:
            os.remove(p)
            p = self.logo_path()
        return {"logo": None}

    # admin -------------------------------------------------------------------------
    def admin_active(self):
        return time.monotonic() <= self._admin_until

    def admin_login(self, password):
        self._throttle("admin")
        if not self.settings.check_admin(password):
            self._failed("admin")
            raise RuleError("Wrong admin password.")
        self._fails.pop("admin", None)
        self._admin_until = time.monotonic() + ADMIN_TTL_S
        return self.admin_view()

    def admin_lock(self):
        self._admin_until = 0.0
        return {}

    def _admin(self):
        if not self.admin_active():
            raise RuleError("Admin is locked. Open admin again with the admin password.")
        self._admin_until = time.monotonic() + ADMIN_TTL_S

    def admin_fix_entry(self, id, changes, reason):
        self._admin()
        e = self.db.fix_entry(id, changes, reason)
        self.cloud.kick()
        return {"entry": e}

    def admin_rename_vehicle(self, old, new, reason):
        self._admin()
        r = self.db.rename_vehicle(old, new, reason)
        self.cloud.kick()
        return r

    def photo_path(self, entry_id, which):
        """Saved photo of an entry or tare record, if it is still on this PC."""
        if which not in ("front", "back"):
            return None
        r = self.db.entry(entry_id) or self.db.one("SELECT * FROM tares WHERE id=?", (entry_id,))
        p = r and r.get(which + "_photo")
        return p if p and os.path.isfile(p) else None

    def entry_history(self, id):
        return {"edits": self.db.edits(id), "photos": {w: bool(self.photo_path(id, w)) for w in ("front", "back")}}

    def admin_run_cleanup(self):
        self._admin()
        return {"report": self.maint.run(), "storage": self.maint.storage()}

    def admin_view(self):
        self._admin()
        lv = self.settings.get("live_view") or {}
        return {"storage": self.maint.storage(), "dbOk": self.db_ok, "settingsRecovered": self.settings.recovered,
                "liveView": {"running": self.liveview.running(), "error": self.liveview.error,
                             "addresses": lan_addresses(), "port": lv.get("port"), "hasPassword": bool(lv.get("password_hash"))},
                "vehicles": [v["vno"] for v in self.db.vehicle_list()],"settings": self.settings.public(), "ports": list_ports(), "brands": BRANDS,
                "counters": {"in": self.db.counter("in"), "out": self.db.counter("out")},
                "dataFolder": paths.data_dir(), "live": self.live(), "logo": self.logo_version()}

    def admin_save(self, patch, operators=None, adminPassword=None, counters=None, liveViewPassword=None):
        self._admin()
        allowed = {"site_name", "agency_name", "weighbridge", "cameras", "cloud", "reports_folder",
                   "outward_destinations", "retention", "live_view"}
        patch = {k: v for k, v in (patch or {}).items() if k in allowed}
        if "retention" in patch:
            patch["retention"] = {k: max(0, int(patch["retention"].get(k) or 0))
                                  for k in ("photos_days", "reports_days", "logs_days", "backups_days")}
        if "live_view" in patch:
            lv = patch["live_view"]
            port = int(lv.get("port") or 8090)
            if not 1024 <= port <= 65535:
                raise RuleError("Live view port must be between 1024 and 65535.")
            patch["live_view"] = {"enabled": bool(lv.get("enabled")), "port": port}
        if liveViewPassword:
            if len(liveViewPassword) < 6:
                raise RuleError("Live view password needs at least 6 characters.")
            if self.settings.check_admin(liveViewPassword):
                raise RuleError("Live view password must be different from the admin password.")
            patch.setdefault("live_view", {})["password_hash"] = hash_password(liveViewPassword)
        if adminPassword:
            problem = password_problem(adminPassword)
            if not problem and self.settings.operator_pin_matches(adminPassword):
                problem = "Admin password must not contain an operator's PIN."
            if problem:
                raise RuleError(problem)
            patch["admin_password_hash"] = hash_password(adminPassword)
        if operators is not None:
            old = {o["name"]: o.get("pin_hash", "") for o in self.settings.data.get("operators", [])}
            ops, names = [], set()
            for o in operators:
                name = (o.get("name") or "").strip()
                if not name:
                    continue
                if name in names:
                    raise RuleError("Two operators are called %s. Names must be different." % name)
                names.add(name)
                pin = (o.get("pin") or "").strip()
                if pin:
                    problem = pin_problem(pin)
                    if problem:
                        raise RuleError("%s: %s" % (name, problem))
                elif not old.get(name):
                    raise RuleError("Give %s a 4-number PIN." % name)
                ops.append({"name": name, "pin_hash": hash_pin(pin) if pin else old[name], "pin": pin})
            if not ops:
                raise RuleError("Keep at least one operator.")
            for i, a in enumerate(ops):  # every operator needs their own PIN
                for b in ops[i + 1:]:
                    pa, pb = a["pin"], b["pin"]
                    if (pa and check_pin(pa, b["pin_hash"])) or (pb and check_pin(pb, a["pin_hash"])):
                        raise RuleError("%s and %s have the same PIN. Each operator needs their own."
                                        % (a["name"], b["name"]))
            self.settings.replace("operators", [{"name": o["name"], "pin_hash": o["pin_hash"]} for o in ops])
        for name, value in (counters or {}).items():
            if name in ("in", "out") and value not in (None, ""):
                if int(value) != self.db.counter(name):
                    self.db.set_counter(name, int(value))
        if patch:
            self.settings.update(patch)
        if "weighbridge" in patch:
            self.wb.restart(self.settings.get("weighbridge"))
        if "cameras" in patch:
            self.cams.restart(self.settings.get("cameras"))
        if "cloud" in patch:
            self.cloud.kick()
        if "live_view" in patch:
            self.liveview.apply()
        return self.admin_view()

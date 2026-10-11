"""Everything the screens can ask for. One method per UI action.

Methods take and return plain JSON-able values. ``RuleError`` messages are
shown to the operator as-is, so they are written in the app's plain voice.
"""
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
from .settings import Settings, hash_pin
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
        self.settings = settings or Settings()
        self.db = database or DB()
        self.wb = Weighbridge(self.settings.get("weighbridge"))
        self.cams = Cameras(self.settings.get("cameras"))
        self.cloud = CloudSync(self.db, self.settings)
        self.operator = None
        self._admin_until = 0.0
        self.window = None  # set by main.py when running in a pywebview window
        self._full = False
        if start_devices:
            self.wb.start()
            self.cams.start()
            self.cloud.start()

    def shutdown(self):
        self.wb.stop()
        self.cams.stop()
        self.cloud.stop()

    # sign-in -------------------------------------------------------------
    def boot(self):
        return {"site": self.settings.get("site_name"), "agency": self.settings.get("agency_name"),
                "operators": self.settings.operator_names(), "defaultPins": self.settings.using_default_pins(),
                "version": __version__, "operator": self.operator, "inWindow": self.window is not None}

    def login(self, name, pin):
        if not self.settings.check_operator(name, pin):
            raise RuleError("Wrong PIN. Try again.")
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
        return {"wb": self.wb.live(), "simulate": bool(self.settings.get("weighbridge").get("simulate")),
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

    def report(self, view, day=None, period=None, dateFrom=None, dateTo=None, dir="Both"):
        d = parse_day(day) if day else dt.date.today()
        if view == "daily":
            return self.db.report_daily(d)
        if view == "shift":
            sh = self.settings.get("shifts")
            return {"rows": self.db.report_shift(d, sh["starts"][:sh["count"]]), "shifts": sh}
        if view == "inc":
            return {"rows": [{"id": r["id"], "vno": r["vno"], "gross": r["gross_kg"],
                              "time": r["created_at"][:16]} for r in self.db.report_incomplete()]}
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
        path = path or self.reports_folder()
        if sys.platform == "win32":
            os.startfile(path)  # noqa: only exists on Windows
        else:
            subprocess.Popen(["xdg-open", path])
        return {}

    # window --------------------------------------------------------------------
    def toggle_full(self, on):
        if self.window is not None and bool(on) != self._full:
            self.window.toggle_fullscreen()
            self._full = bool(on)
        return {"full": self._full}

    # admin -----------------------------------------------------------------------
    def admin_login(self, pin):
        if not self.settings.check_admin(pin):
            raise RuleError("Wrong admin PIN.")
        self._admin_until = time.monotonic() + ADMIN_TTL_S
        return self.admin_view()

    def _admin(self):
        if time.monotonic() > self._admin_until:
            raise RuleError("Admin sign-in timed out. Type the admin PIN again.")
        self._admin_until = time.monotonic() + ADMIN_TTL_S

    def admin_view(self):
        self._admin()
        return {"settings": self.settings.public(), "ports": list_ports(),
                "counters": {"in": self.db.counter("in"), "out": self.db.counter("out")},
                "dataFolder": paths.data_dir(), "live": self.live()}

    def admin_save(self, patch, operators=None, adminPin=None, counters=None):
        self._admin()
        allowed = {"site_name", "agency_name", "weighbridge", "cameras", "cloud", "reports_folder",
                   "outward_destinations"}
        patch = {k: v for k, v in (patch or {}).items() if k in allowed}
        if adminPin:
            if not (str(adminPin).isdigit() and len(str(adminPin)) == 4):
                raise RuleError("Admin PIN must be 4 numbers.")
            patch["admin_pin_hash"] = hash_pin(adminPin)
        if operators is not None:
            old = {o["name"]: o.get("pin_hash", "") for o in self.settings.data.get("operators", [])}
            ops = []
            for o in operators:
                name = (o.get("name") or "").strip()
                if not name:
                    continue
                pin = (o.get("pin") or "").strip()
                if pin and not (pin.isdigit() and len(pin) == 4):
                    raise RuleError("PIN for %s must be 4 numbers." % name)
                ops.append({"name": name, "pin_hash": hash_pin(pin) if pin else old.get(name, "")})
            if not ops:
                raise RuleError("Keep at least one operator.")
            self.settings.replace("operators", ops)
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
        return self.admin_view()


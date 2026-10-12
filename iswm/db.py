"""SQLite store for every record the plant makes.

Rules from the design:
  * A vehicle gets one empty (tare) weight for its whole life.
  * An inward trip from a vehicle without a tare is saved with its gross
    and stays incomplete until the vehicle is weighed empty on screen 4.
  * Net weight counts in reports only for complete records (gross + tare).
  * Ticket numbers: IN + R/C + YYMM + serial for inward, O + YYMM + serial
    for outward. One counter per direction that never resets, so a ticket
    number can never repeat.
  * Operators cannot change a saved entry; they ask the admin, and only the
    admin can fix it. Every change keeps the old value in entry_edits.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import threading

from . import paths

IN_TYPES = ["Mixed", "Wet", "Dry"]
MATERIALS = ["Compost", "RDF bales", "Recyclables", "Non recyclables", "Metal scrap", "Glass scrap", "Disposal"]
RECYC = [["pet", "PET"], ["hdpe", "HDPE"], ["ldpe", "LDPE film"], ["paper", "Paper and cardboard"],
         ["metal", "Metal"], ["glass", "Glass"], ["other", "Other"]]

SCHEMA = """
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS vehicles (
  vkey TEXT PRIMARY KEY, vno TEXT NOT NULL, tare_kg REAL, tare_at TEXT, tare_id TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
  id TEXT PRIMARY KEY, dir TEXT NOT NULL, vkey TEXT NOT NULL, vno TEXT NOT NULL,
  source TEXT, waste_type TEXT, material TEXT, dest TEXT,
  gross_kg REAL, tare_kg REAL, net_kg REAL,
  manual INTEGER NOT NULL DEFAULT 0, manual_reason TEXT,
  operator TEXT, created_at TEXT NOT NULL, completed_at TEXT,
  front_photo TEXT, back_photo TEXT, batch_id TEXT
);
CREATE INDEX IF NOT EXISTS entries_created ON entries(created_at);
CREATE TABLE IF NOT EXISTS tares (
  id TEXT PRIMARY KEY, vkey TEXT NOT NULL, vno TEXT NOT NULL, tare_kg REAL NOT NULL,
  completes TEXT, operator TEXT, created_at TEXT NOT NULL, front_photo TEXT, back_photo TEXT
);
CREATE TABLE IF NOT EXISTS batches (
  id TEXT PRIMARY KEY, process_date TEXT, entry_ids TEXT, outputs TEXT,
  input_kg REAL, recovered_kg REAL, disposal_kg REAL, operator TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL, sample_kg REAL, wet_kg REAL,
  dry_kg REAL, inert_kg REAL, operator TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL, reason TEXT NOT NULL,
  operator TEXT, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting'
);
CREATE TABLE IF NOT EXISTS entry_edits (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL, field TEXT NOT NULL, old TEXT, new TEXT,
  reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS destinations (name TEXT PRIMARY KEY, last_used TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ref TEXT NOT NULL, label TEXT,
  created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, sent_at TEXT
);
"""


class RuleError(Exception):
    """A save that breaks a plant rule. The message is shown to the operator."""


def now():
    return dt.datetime.now().replace(microsecond=0)


def ts(d=None):
    return (d or now()).strftime("%Y-%m-%d %H:%M:%S")


def norm_vno(s):
    s = re.sub(r"[^A-Z0-9 ]", "", (s or "").upper())
    return re.sub(r"\s+", " ", s).strip()


def vkey(s):
    return norm_vno(s).replace(" ", "")


def yymm(d=None):
    d = d or now()
    return "%02d%02d" % (d.year % 100, d.month)


def ticket_in(source, serial, d=None):
    return "IN" + ("C" if source == "Commercial" else "R") + yymm(d) + "%04d" % serial


def ticket_out(serial, d=None):
    return "O" + yymm(d) + "%04d" % serial


def mins(t):
    a, _, b = (t or "0:0").partition(":")
    return int(a or 0) * 60 + int(b or 0)


def shift_index(hhmm, starts):
    """Which shift a time of day falls in. The last shift runs past midnight."""
    m, ss = mins(hhmm), [mins(s) for s in starts]
    for i, a in enumerate(ss):
        b = ss[(i + 1) % len(ss)]
        inside = (a <= m < b) if a <= b else (m >= a or m < b)
        if inside:
            return i
    return len(ss) - 1


class DB:
    def __init__(self, path=None):
        self.path = path or os.path.join(paths.data_dir(), "iswm.sqlite3")
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")  # every save is on disk before Save says done
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        for table in ("entries", "tares"):  # photos from added cameras: {"cam3": path, ...}
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(%s)" % table)]
            if "extra_photos" not in cols:
                self.conn.execute("ALTER TABLE %s ADD COLUMN extra_photos TEXT" % table)
        for name, start in (("in", 1), ("out", 1), ("batch", 1), ("tare", 1)):
            self.conn.execute("INSERT OR IGNORE INTO counters VALUES (?, ?)", (name, start))

    # helpers ---------------------------------------------------------
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def _take(self, name):
        value = self.conn.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()[0]
        self.conn.execute("UPDATE counters SET value=? WHERE name=?", (value + 1, name))
        return value

    def counter(self, name):
        return self.one("SELECT value FROM counters WHERE name=?", (name,))["value"]

    def set_counter(self, name, value):
        """Admin: start serials at a given number (e.g. to continue from an old system).
        Never lets a counter go backwards, so tickets cannot repeat."""
        with self.lock:
            cur = self.counter(name)
            if int(value) < cur:
                raise RuleError("Serial can only move forward (now %d)." % cur)
            self.conn.execute("UPDATE counters SET value=? WHERE name=?", (int(value), name))

    def _queue(self, kind, ref, label):
        self.conn.execute("INSERT INTO sync_queue(kind, ref, label, created_at) VALUES (?,?,?,?)",
                          (kind, ref, label, ts()))

    def _touch_vehicle(self, vno):
        key, t = vkey(vno), ts()
        self.conn.execute(
            "INSERT INTO vehicles(vkey, vno, first_seen, last_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(vkey) DO UPDATE SET last_seen=excluded.last_seen", (key, norm_vno(vno), t, t))
        return key

    # vehicles --------------------------------------------------------
    def vehicle(self, vno):
        return self.one("SELECT * FROM vehicles WHERE vkey=?", (vkey(vno),))

    def pending(self):
        return self.q("SELECT id, vno, vkey, gross_kg, created_at FROM entries "
                      "WHERE dir='in' AND net_kg IS NULL ORDER BY created_at")

    def vehicle_status(self, flow, vno):
        if not vno:
            return None
        v = self.vehicle(vno)
        has_tare = bool(v and v["tare_kg"] is not None)
        pend = self.one("SELECT 1 AS x FROM entries WHERE dir='in' AND net_kg IS NULL AND vkey=?", (vkey(vno),))
        if flow == "tare":
            return "hasTare" if has_tare else "pending" if pend else "new"
        if pend:
            return "pending"
        return "known" if has_tare else "new"

    def vehicle_list(self):
        return self.q("SELECT vno, tare_kg FROM vehicles ORDER BY last_seen DESC")

    def destinations(self, defaults):
        used = [r["name"] for r in self.q("SELECT name FROM destinations ORDER BY last_used DESC")]
        return (used + [d for d in defaults if d not in used])[:8]

    # saves -----------------------------------------------------------
    def save_inward(self, vno, source, waste_type, gross, operator, photos=(None, None)):
        vno = norm_vno(vno)
        if not vno:
            raise RuleError("Pick the vehicle.")
        if source not in ("Residential", "Commercial") or waste_type not in IN_TYPES:
            raise RuleError("Pick From and Waste.")
        with self.lock:
            if self.vehicle_status("in", vno) == "pending":
                raise RuleError("This vehicle is waiting for its empty weight. Weigh it empty on yellow 4 first.")
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                key = self._touch_vehicle(vno)
                v = self.vehicle(vno)
                tare = v["tare_kg"] if v else None
                net = max(0.0, gross - tare) if tare is not None else None
                id_ = ticket_in(source, self._take("in"))
                t = ts()
                self.conn.execute(
                    "INSERT INTO entries(id, dir, vkey, vno, source, waste_type, gross_kg, tare_kg, net_kg, "
                    "operator, created_at, completed_at, front_photo, back_photo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (id_, "in", key, vno, source, waste_type, gross, tare, net, operator, t,
                     t if net is not None else None, photos[0], photos[1]))
                self._queue("entry", id_, "Inward")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return self.entry(id_)

    def save_outward(self, vno, material, dest, gross, operator, manual_kg=None, reason=None, photos=(None, None)):
        vno, dest = norm_vno(vno), (dest or "").strip()
        if material not in MATERIALS:
            raise RuleError("Pick the material.")
        if not dest:
            raise RuleError("Type where it is going.")
        manual = manual_kg is not None
        if manual and (not reason or not manual_kg or manual_kg <= 0):
            raise RuleError("Type the small scale weight and pick a reason.")
        with self.lock:
            if self.vehicle_status("out", vno) != "known":
                raise RuleError("No empty weight yet. Weigh it empty first.")
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                key = self._touch_vehicle(vno)
                tare = self.vehicle(vno)["tare_kg"]
                net = float(manual_kg) if manual else max(0.0, gross - tare)
                id_ = ticket_out(self._take("out"))
                t = ts()
                self.conn.execute(
                    "INSERT INTO entries(id, dir, vkey, vno, material, dest, gross_kg, tare_kg, net_kg, manual, "
                    "manual_reason, operator, created_at, completed_at, front_photo, back_photo) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (id_, "out", key, vno, material, dest, None if manual else gross, None if manual else tare,
                     net, 1 if manual else 0, reason, operator, t, t, photos[0], photos[1]))
                self.conn.execute("INSERT INTO destinations VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET "
                                  "last_used=excluded.last_used", (dest, t))
                self._queue("entry", id_, "Outward")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return self.entry(id_)

    def save_tare(self, vno, weight, operator, photos=(None, None)):
        vno = norm_vno(vno)
        with self.lock:
            st = self.vehicle_status("tare", vno)
            if st == "hasTare":
                raise RuleError("This vehicle already has an empty weight.")
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                key = self._touch_vehicle(vno)
                t = ts()
                tid = "T" + yymm() + "%04d" % self._take("tare")
                pend = self.conn.execute("SELECT id, gross_kg FROM entries WHERE dir='in' AND net_kg IS NULL "
                                         "AND vkey=?", (key,)).fetchall()
                self.conn.execute("UPDATE vehicles SET tare_kg=?, tare_at=?, tare_id=? WHERE vkey=?",
                                  (weight, t, tid, key))
                for p in pend:
                    self.conn.execute("UPDATE entries SET tare_kg=?, net_kg=?, completed_at=? WHERE id=?",
                                      (weight, max(0.0, p["gross_kg"] - weight), t, p["id"]))
                    self._queue("entry", p["id"], "Inward complete")
                self.conn.execute(
                    "INSERT INTO tares(id, vkey, vno, tare_kg, completes, operator, created_at, front_photo, back_photo) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (tid, key, vno, weight, ",".join(p["id"] for p in pend) or None, operator, t,
                     photos[0], photos[1]))
                self._queue("tare", tid, "Empty weight")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return {"tare": self.one("SELECT * FROM tares WHERE id=?", (tid,)),
                "completed": [self.entry(p["id"]) for p in pend]}

    def set_photos(self, table, id_, photos):
        """photos: {camera: path}. Front and back have their own columns, the rest go in extra_photos."""
        assert table in ("entries", "tares")
        extra = {k: v for k, v in photos.items() if k not in ("front", "back") and v}
        with self.lock:
            self.conn.execute("UPDATE %s SET front_photo=?, back_photo=?, extra_photos=? WHERE id=?" % table,
                              (photos.get("front"), photos.get("back"), json.dumps(extra) if extra else None, id_))

    def entry(self, id_):
        return self.one("SELECT * FROM entries WHERE id=?", (id_,))

    # admin fixes -------------------------------------------------------
    EDITABLE = {"vno", "source", "waste_type", "material", "dest"}

    def fix_entry(self, entry_id, changes, reason):
        """Admin correction. The old values are kept in entry_edits; the ticket number never changes."""
        reason = (reason or "").strip()
        if not reason:
            raise RuleError("Say why it is being changed.")
        with self.lock:
            e = self.entry(entry_id)
            if not e:
                raise RuleError("Entry not found.")
            ch = {k: (v.strip() if isinstance(v, str) else v) for k, v in (changes or {}).items()
                  if k in self.EDITABLE and v not in (None, "")}
            if "vno" in ch:
                ch["vno"] = norm_vno(ch["vno"])
                if not ch["vno"]:
                    raise RuleError("Type the vehicle number.")
            if e["dir"] == "in":
                ch.pop("material", None); ch.pop("dest", None)
                if "source" in ch and ch["source"] not in ("Residential", "Commercial"):
                    raise RuleError("From must be Residential or Commercial.")
                if "waste_type" in ch and ch["waste_type"] not in IN_TYPES:
                    raise RuleError("Waste must be Mixed, Wet or Dry.")
            else:
                ch.pop("source", None); ch.pop("waste_type", None)
                if "material" in ch and ch["material"] not in MATERIALS:
                    raise RuleError("Pick a material from the list.")
            ch = {k: v for k, v in ch.items() if str(e.get(k) or "") != str(v)}
            if not ch:
                raise RuleError("Nothing was changed.")
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                t = ts()
                for k, v in ch.items():
                    self.conn.execute("INSERT INTO entry_edits(entry_id, field, old, new, reason, created_at) "
                                      "VALUES (?,?,?,?,?,?)", (entry_id, k, e.get(k), v, reason, t))
                if "vno" in ch:
                    key = self._touch_vehicle(ch["vno"])
                    self.conn.execute("UPDATE entries SET vkey=?, vno=? WHERE id=?", (key, ch["vno"], entry_id))
                    v = self.conn.execute("SELECT tare_kg FROM vehicles WHERE vkey=?", (key,)).fetchone()
                    if e["dir"] == "in" and e["net_kg"] is None and v and v["tare_kg"] is not None:
                        # the right vehicle already has an empty weight, so the trip is now complete
                        self.conn.execute("UPDATE entries SET tare_kg=?, net_kg=?, completed_at=? WHERE id=?",
                                          (v["tare_kg"], max(0.0, e["gross_kg"] - v["tare_kg"]), t, entry_id))
                for k in ("source", "waste_type", "material", "dest"):
                    if k in ch:
                        self.conn.execute("UPDATE entries SET %s=? WHERE id=?" % k, (ch[k], entry_id))
                self.conn.execute("UPDATE corrections SET status='done' WHERE entry_id=?", (entry_id,))
                self._queue("entry", entry_id, "Fixed by admin")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return self.entry(entry_id)

    def rename_vehicle(self, old, new, reason):
        """Fix a wrongly typed vehicle number everywhere (merges into the right one if it exists)."""
        old_v, new_n = self.vehicle(old), norm_vno(new)
        if not old_v:
            raise RuleError("No vehicle %s." % norm_vno(old))
        if not new_n or vkey(new_n) == old_v["vkey"] and new_n == old_v["vno"]:
            raise RuleError("Type the right vehicle number.")
        if not (reason or "").strip():
            raise RuleError("Say why it is being changed.")
        with self.lock:
            target = self.vehicle(new_n)
            if target and target["vkey"] != old_v["vkey"] and None not in (target["tare_kg"], old_v["tare_kg"]) \
                    and abs(target["tare_kg"] - old_v["tare_kg"]) > 0.5:
                raise RuleError("Both numbers already have different empty weights. Fix the trips one by one instead.")
            ids = [r["id"] for r in self.q("SELECT id FROM entries WHERE vkey=?", (old_v["vkey"],))]
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                t, nkey = ts(), vkey(new_n)
                if target and target["vkey"] != old_v["vkey"]:
                    if target["tare_kg"] is None and old_v["tare_kg"] is not None:
                        self.conn.execute("UPDATE vehicles SET tare_kg=?, tare_at=?, tare_id=? WHERE vkey=?",
                                          (old_v["tare_kg"], old_v["tare_at"], old_v["tare_id"], nkey))
                    self.conn.execute("DELETE FROM vehicles WHERE vkey=?", (old_v["vkey"],))
                else:
                    self.conn.execute("UPDATE vehicles SET vkey=?, vno=?, last_seen=? WHERE vkey=?",
                                      (nkey, new_n, t, old_v["vkey"]))
                for i in ids:
                    self.conn.execute("INSERT INTO entry_edits(entry_id, field, old, new, reason, created_at) "
                                      "VALUES (?,?,?,?,?,?)", (i, "vno", old_v["vno"], new_n, reason.strip(), t))
                    self._queue("entry", i, "Vehicle number fixed")
                self.conn.execute("UPDATE entries SET vkey=?, vno=? WHERE vkey=?", (nkey, new_n, old_v["vkey"]))
                self.conn.execute("UPDATE tares SET vkey=?, vno=? WHERE vkey=?", (nkey, new_n, old_v["vkey"]))
                tare = self.conn.execute("SELECT tare_kg FROM vehicles WHERE vkey=?", (nkey,)).fetchone()
                if tare and tare["tare_kg"] is not None:  # pending trips of the merged vehicle become complete
                    for p in self.conn.execute("SELECT id, gross_kg FROM entries WHERE vkey=? AND dir='in' AND "
                                               "net_kg IS NULL", (nkey,)).fetchall():
                        self.conn.execute("UPDATE entries SET tare_kg=?, net_kg=?, completed_at=? WHERE id=?",
                                          (tare["tare_kg"], max(0.0, p["gross_kg"] - tare["tare_kg"]), t, p["id"]))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return {"vno": new_n, "trips": len(ids)}

    def edits(self, entry_id):
        return self.q("SELECT field, old, new, reason, created_at FROM entry_edits WHERE entry_id=? ORDER BY id",
                      (entry_id,))

    # durability -----------------------------------------------------------
    def kv_get(self, key):
        r = self.one("SELECT value FROM kv WHERE key=?", (key,))
        return r["value"] if r else None

    def kv_set(self, key, value):
        with self.lock:
            self.conn.execute("INSERT INTO kv VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                              "updated_at=excluded.updated_at", (key, value, ts()))

    def integrity_ok(self):
        try:
            return self.one("PRAGMA quick_check")["quick_check"] == "ok"
        except sqlite3.DatabaseError:
            return False

    def backup_to(self, path):
        """Consistent copy of the live database (safe while the app is running)."""
        tmp = path + ".tmp"
        with self.lock:
            dst = sqlite3.connect(tmp)
            try:
                self.conn.backup(dst)
            finally:
                dst.close()
        os.replace(tmp, path)

    # material recovery -------------------------------------------------
    def unprocessed_trips(self, days=7):
        since = ts(now() - dt.timedelta(days=days))
        return self.q("SELECT id, vno, waste_type, net_kg, created_at FROM entries WHERE dir='in' "
                      "AND net_kg IS NOT NULL AND batch_id IS NULL AND created_at>=? ORDER BY created_at", (since,))

    def save_batch(self, process_date, entry_ids, outputs, operator):
        if not entry_ids:
            raise RuleError("Tick the trips you processed.")
        vals = {k: float(v or 0) for k, v in (outputs or {}).items()}
        recyc = sum(vals.get(k, 0) for k, _ in RECYC)
        recovered = vals.get("compost", 0) + vals.get("rdf", 0) + recyc
        disposal = vals.get("disposal", 0)
        if recovered + disposal <= 0:
            raise RuleError("Type what came out, in kg.")
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                marks = ",".join("?" * len(entry_ids))
                rows = self.conn.execute(
                    "SELECT id, net_kg FROM entries WHERE id IN (%s) AND batch_id IS NULL AND net_kg IS NOT NULL"
                    % marks, entry_ids).fetchall()
                if len(rows) != len(entry_ids):
                    raise RuleError("Some trips were already processed. Tick them again.")
                bid = "B-%04d" % self._take("batch")
                input_kg = sum(r["net_kg"] for r in rows)
                self.conn.execute("INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?)",
                                  (bid, process_date, json.dumps(entry_ids), json.dumps(vals), input_kg,
                                   recovered, disposal, operator, ts()))
                self.conn.execute("UPDATE entries SET batch_id=? WHERE id IN (%s)" % marks, [bid, *entry_ids])
                self._queue("batch", bid, "Recovery batch")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return {"id": bid, "trips": len(entry_ids)}

    def sample_due(self):
        return not self.one("SELECT 1 AS x FROM samples WHERE month=?", (now().strftime("%Y-%m"),))

    def save_sample(self, kg, wet, dry, inert, operator):
        if not kg or kg <= 0 or (wet + dry + inert) <= 0:
            raise RuleError("Type the sample weight and its parts.")
        with self.lock:
            cur = self.conn.execute("INSERT INTO samples(month, sample_kg, wet_kg, dry_kg, inert_kg, operator, "
                                    "created_at) VALUES (?,?,?,?,?,?,?)",
                                    (now().strftime("%Y-%m"), kg, wet, dry, inert, operator, ts()))
            self._queue("sample", str(cur.lastrowid), "Mixed sample")

    # corrections -------------------------------------------------------
    def ask_correction(self, entry_id, reason, operator):
        reason = (reason or "").strip()
        if not reason:
            raise RuleError("Say what is wrong.")
        if not self.entry(entry_id):
            raise RuleError("Entry not found.")
        with self.lock:
            cur = self.conn.execute("INSERT INTO corrections(entry_id, reason, operator, created_at) "
                                    "VALUES (?,?,?,?)", (entry_id, reason, operator, ts()))
            self._queue("correction", str(cur.lastrowid), "Correction request")

    # sync queue --------------------------------------------------------
    def queue_waiting(self):
        return self.q("SELECT * FROM sync_queue WHERE sent_at IS NULL ORDER BY id")

    def queue_done(self, qid):
        with self.lock:
            self.conn.execute("UPDATE sync_queue SET sent_at=?, last_error=NULL WHERE id=?", (ts(), qid))

    def queue_failed(self, qid, err):
        with self.lock:
            self.conn.execute("UPDATE sync_queue SET attempts=attempts+1, last_error=? WHERE id=?",
                              (str(err)[:300], qid))

    def payload(self, kind, ref):
        if kind == "entry":
            return self.entry(ref)
        if kind == "tare":
            return self.one("SELECT * FROM tares WHERE id=?", (ref,))
        if kind == "batch":
            b = self.one("SELECT * FROM batches WHERE id=?", (ref,))
            if b:
                b["entry_ids"], b["outputs"] = json.loads(b["entry_ids"]), json.loads(b["outputs"])
            return b
        if kind == "sample":
            return self.one("SELECT * FROM samples WHERE id=?", (int(ref),))
        if kind == "correction":
            return self.one("SELECT * FROM corrections WHERE id=?", (int(ref),))
        return None

    # screens -----------------------------------------------------------
    def today_entries(self):
        day = now().strftime("%Y-%m-%d")
        rows = self.q("SELECT e.*, (SELECT COUNT(*) FROM corrections c WHERE c.entry_id=e.id) AS asked "
                      "FROM entries e WHERE substr(created_at,1,10)=? ORDER BY created_at DESC", (day,))
        return rows

    # reports -----------------------------------------------------------
    def entries_between(self, start, end):
        return self.q("SELECT * FROM entries WHERE created_at>=? AND created_at<? ORDER BY created_at",
                      (ts(start), ts(end)))

    @staticmethod
    def _agg(rows):
        done = [r for r in rows if r["net_kg"] is not None]
        return {"trips": len(done), "inc": len(rows) - len(done), "net": sum(r["net_kg"] for r in done)}

    def report_daily(self, day):
        start = dt.datetime.combine(day, dt.time())
        rows = self.entries_between(start, start + dt.timedelta(days=1))
        out = {}
        for d, mats, key in (("in", IN_TYPES, "waste_type"), ("out", MATERIALS, "material")):
            dr = [r for r in rows if r["dir"] == d]
            out[d] = {"total": self._agg(dr),
                      "rows": [{"label": m, **self._agg([r for r in dr if r[key] == m])} for m in mats]}
        return out

    def report_shift(self, day, starts):
        """Shift day D runs from D at the first shift start to D+1 at the first shift start."""
        first = mins(starts[0])
        start = dt.datetime.combine(day, dt.time(first // 60, first % 60))
        rows = self.entries_between(start, start + dt.timedelta(days=1))
        for r in rows:
            r["shift"] = shift_index(r["created_at"][11:16], starts)

        def line(label, d, mat, total):
            key = "waste_type" if d == "in" else "material"
            sel = [r for r in rows if r["dir"] == d and (mat is None or r[key] == mat)]
            return {"label": label, "dir": d, "total": total,
                    "cells": [self._agg([r for r in sel if r["shift"] == i]) for i in range(len(starts))]}

        out_mats = [m for m in MATERIALS if any(r["dir"] == "out" and r["material"] == m for r in rows)]
        return ([line("All inward", "in", None, True)] + [line(m, "in", m, False) for m in IN_TYPES] +
                [line("All outward", "out", None, True)] + [line(m, "out", m, False) for m in out_mats])

    def report_incomplete(self):
        return self.q("SELECT id, vno, gross_kg, created_at FROM entries WHERE dir='in' AND net_kg IS NULL "
                      "ORDER BY created_at")

    def trips(self, d_from, d_to, direction="Both", status="All", query="", limit=2000):
        start = dt.datetime.combine(d_from, dt.time())
        end = dt.datetime.combine(d_to, dt.time()) + dt.timedelta(days=1)
        sql = ("SELECT e.*, (SELECT reason FROM corrections c WHERE c.entry_id=e.id AND c.status='waiting' "
               "ORDER BY c.id DESC LIMIT 1) AS asked, (SELECT COUNT(*) FROM entry_edits x WHERE x.entry_id=e.id) "
               "AS edits FROM entries e WHERE created_at>=? AND created_at<?")
        args = [ts(start), ts(end)]
        if direction in ("Inward", "Outward"):
            sql += " AND dir=?"; args.append("in" if direction == "Inward" else "out")
        if status == "Complete":
            sql += " AND net_kg IS NOT NULL"
        elif status == "Incomplete":
            sql += " AND net_kg IS NULL"
        elif status == "Asked":
            sql += " AND EXISTS (SELECT 1 FROM corrections c WHERE c.entry_id=e.id AND c.status='waiting')"
        q = vkey(query)
        if q:
            sql += " AND (vkey LIKE ? OR id LIKE ?)"; args += ["%" + q + "%", "%" + q + "%"]
        return self.q(sql + " ORDER BY created_at DESC LIMIT %d" % int(limit), args)

    def report_by_vehicle(self, d_from, d_to, direction):
        start = dt.datetime.combine(d_from, dt.time())
        end = dt.datetime.combine(d_to, dt.time()) + dt.timedelta(days=1)
        rows = [r for r in self.entries_between(start, end) if r["net_kg"] is not None and
                (direction == "Both" or r["dir"] == ("in" if direction == "Inward" else "out"))]
        by = {}
        for r in rows:
            b = by.setdefault(r["vno"], {"label": r["vno"], "trips": 0, "in_net": 0.0, "out_net": 0.0})
            b["trips"] += 1
            b["in_net" if r["dir"] == "in" else "out_net"] += r["net_kg"]
        return sorted(by.values(), key=lambda b: -(b["in_net"] + b["out_net"]))

    def report_custom(self, period, d_from, d_to, direction):
        if period == "Vehicle":
            return self.report_by_vehicle(d_from, d_to, direction)
        start = dt.datetime.combine(d_from, dt.time())
        end = dt.datetime.combine(d_to, dt.time()) + dt.timedelta(days=1)
        rows = [r for r in self.entries_between(start, end) if r["net_kg"] is not None]
        if direction == "Inward":
            rows = [r for r in rows if r["dir"] == "in"]
        elif direction == "Outward":
            rows = [r for r in rows if r["dir"] == "out"]
        buckets = []
        if period == "Hourly":
            cur = start
            while cur < end and len(buckets) < 24 * 62:
                buckets.append((cur, cur + dt.timedelta(hours=1),
                                cur.strftime("%d %b %Y · %H:00–") + "%02d:00" % ((cur.hour + 1) % 24)))
                cur += dt.timedelta(hours=1)
        elif period == "Daily":
            cur = start
            while cur < end and len(buckets) < 400:
                buckets.append((cur, cur + dt.timedelta(days=1), cur.strftime("%d %b %Y")))
                cur += dt.timedelta(days=1)
        elif period == "Weekly":
            cur = start
            while cur < end and len(buckets) < 120:
                nxt = min(cur + dt.timedelta(days=7), end)
                buckets.append((cur, nxt, cur.strftime("%d %b") + " – " + (nxt - dt.timedelta(days=1)).strftime("%d %b %Y")))
                cur = nxt
        else:
            cur = start.replace(day=1)
            while cur < end and len(buckets) < 120:
                nxt = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
                buckets.append((max(cur, start), min(nxt, end), cur.strftime("%B %Y")))
                cur = nxt
        out = []
        for a, b, label in buckets:
            sa, sb = ts(a), ts(b)
            sel = [r for r in rows if sa <= r["created_at"] < sb]
            if period == "Hourly" and not sel:
                continue
            out.append({"label": label, "trips": len(sel),
                        "in_net": sum(r["net_kg"] for r in sel if r["dir"] == "in"),
                        "out_net": sum(r["net_kg"] for r in sel if r["dir"] == "out")})
        return out

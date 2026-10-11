import datetime as dt
import time

import pytest

from iswm.db import DB, RuleError, shift_index, ticket_in, ticket_out, yymm
from iswm.service import Service
from iswm.settings import Settings, check_pin, hash_pin
from iswm.weighbridge import Weighbridge


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.sqlite3"))


def test_ticket_format():
    d = dt.datetime(2026, 10, 5)
    assert ticket_in("Residential", 1, d) == "INR26100001"
    assert ticket_in("Commercial", 43, d) == "INC26100043"
    assert ticket_out(318, d) == "O26100318"


def test_inward_without_tare_is_incomplete_until_tare(db):
    e = db.save_inward("ap 39 ub 7712", "Residential", "Mixed", 6240, "Op")
    assert e["id"] == "INR" + yymm() + "0001"
    assert e["net_kg"] is None and e["vno"] == "AP 39 UB 7712"
    assert [p["id"] for p in db.pending()] == [e["id"]]
    # a pending vehicle cannot come in again, nor go out
    with pytest.raises(RuleError):
        db.save_inward("AP39UB7712", "Residential", "Mixed", 5000, "Op")
    with pytest.raises(RuleError):
        db.save_outward("AP 39 UB 7712", "Compost", "Farm", 5000, "Op")
    r = db.save_tare("AP 39 UB 7712", 2600, "Op")
    assert r["completed"][0]["net_kg"] == 3640
    assert db.pending() == []
    # tare is once per lifetime
    with pytest.raises(RuleError):
        db.save_tare("AP 39 UB 7712", 2500, "Op")
    e2 = db.save_inward("AP 39 UB 7712", "Commercial", "Wet", 5600, "Op")
    assert e2["net_kg"] == 3000 and e2["id"].startswith("INC") and e2["id"].endswith("0002")


def test_counters_never_repeat_or_go_back(db):
    db.save_tare("AP 21 TA 7781", 2700, "Op")
    a = db.save_outward("AP 21 TA 7781", "Compost", "Farm", 4000, "Op")
    b = db.save_outward("AP 21 TA 7781", "Compost", "Farm", 4100, "Op", manual_kg=850, reason="Load too small")
    assert a["id"] != b["id"] and b["manual"] == 1 and b["net_kg"] == 850
    with pytest.raises(RuleError):
        db.set_counter("out", 1)
    db.set_counter("out", 500)
    assert db.save_outward("AP 21 TA 7781", "RDF bales", "Cement", 6000, "Op")["id"].endswith("0500")


def test_reports_count_only_complete(db):
    db.save_tare("AP 39 UA 4521", 5420, "Op")
    db.save_inward("AP 39 UA 4521", "Residential", "Mixed", 8540, "Op")
    db.save_inward("AP 21 TD 0418", "Commercial", "Mixed", 3980, "Op")
    rep = db.report_daily(dt.date.today())
    assert rep["in"]["total"] == {"trips": 1, "inc": 1, "net": 3120}
    rows = db.report_custom("Daily", dt.date.today(), dt.date.today(), "Both")
    assert rows[0]["trips"] == 1 and rows[0]["in_net"] == 3120
    assert len(db.report_incomplete()) == 1


def test_batch_marks_trips_processed(db):
    db.save_tare("AP 39 UA 4521", 5000, "Op")
    e = db.save_inward("AP 39 UA 4521", "Residential", "Mixed", 8000, "Op")
    assert [t["id"] for t in db.unprocessed_trips()] == [e["id"]]
    r = db.save_batch("2026-10-11", [e["id"]], {"compost": 1200, "disposal": 900}, "Op")
    assert r["id"] == "B-0001" and db.unprocessed_trips() == []
    with pytest.raises(RuleError):
        db.save_batch("2026-10-11", [e["id"]], {"compost": 1}, "Op")


def test_shift_index_wraps_midnight():
    starts = ["06:00", "14:00", "22:00"]
    assert shift_index("06:00", starts) == 0
    assert shift_index("13:59", starts) == 0
    assert shift_index("14:00", starts) == 1
    assert shift_index("23:30", starts) == 2
    assert shift_index("03:10", starts) == 2


def test_pins():
    assert check_pin("0000", "")
    stored = hash_pin("4821")
    assert check_pin("4821", stored) and not check_pin("0000", stored)


def test_weighbridge_parse_and_stability():
    wb = Weighbridge({"regex_pattern": r"(\d+\.?\d*)", "weight_multiplier": 1, "stable_seconds": 0.3,
                      "stable_tolerance_kg": 10, "min_weight_kg": 10})
    assert wb.parse("ST,GS,+0006240kg") == 6240
    assert wb.parse("garbage") is None
    for w in (6000, 6200, 6240, 6240):
        wb._push(w)
        time.sleep(0.12)
    assert wb.live()["connected"]
    for _ in range(4):
        wb._push(6240)
        time.sleep(0.1)
    assert wb.live()["stable"] and wb.capture() == 6240


def test_service_save_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("ISWM_DATA_DIR", str(tmp_path))
    svc = Service(Settings(str(tmp_path / "s.json")), DB(str(tmp_path / "d.sqlite3")), start_devices=False)
    with pytest.raises(RuleError):
        svc.save_in("AP 39 UA 4521", "Residential", "Mixed")  # not signed in
    svc.login("Operator 1", "0000")
    with pytest.raises(RuleError):
        svc.save_in("AP 39 UA 4521", "Residential", "Mixed")  # no steady weight
    monkeypatch.setattr(svc.wb, "capture", lambda: 7000.0)
    r = svc.save_in("AP 39 UA 4521", "Residential", "Mixed")
    assert r["entry"]["gross_kg"] == 7000 and r["photos"] == 0
    st = svc.state()
    assert st["pending"][0]["vno"] == "AP 39 UA 4521" and st["nextIn"] == 2
    path = svc.export_csv("Daily", dt.date.today().isoformat(), dt.date.today().isoformat())["path"]
    assert open(path, encoding="utf-8-sig").readline().startswith("Period,Trips")


def test_serial_reader_over_socket():
    """The real read loop, fed by a fake indicator on a TCP socket."""
    import socket
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def indicator():
        conn, _ = srv.accept()
        while not stop.is_set():
            conn.sendall(b"ST,GS,+0012340kg\r\n")
            time.sleep(0.05)
        conn.close()

    threading.Thread(target=indicator, daemon=True).start()
    wb = Weighbridge({"simulate": False, "com_port": "socket://127.0.0.1:%d" % port,
                      "regex_pattern": r"(\d+\.?\d*)", "stable_seconds": 0.5, "stable_tolerance_kg": 10,
                      "min_weight_kg": 10})
    wb.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline and wb.capture() is None:
            time.sleep(0.1)
        assert wb.capture() == 12340
    finally:
        stop.set()
        wb.stop()
        srv.close()


def test_cloud_sync_drains_queue_with_fake_bucket(tmp_path):
    from iswm.cloud import CloudSync

    uploaded = {}

    class Blob:
        def __init__(self, name):
            self.name = name

        def upload_from_string(self, data, **kw):
            uploaded[self.name] = data

        def upload_from_filename(self, path, **kw):
            uploaded[self.name] = path

    class Bucket:
        def blob(self, name):
            return Blob(name)

    s = Settings(str(tmp_path / "s.json"))
    s.update({"cloud": {"enabled": True, "bucket_name": "b"}})
    d = DB(str(tmp_path / "d.sqlite3"))
    d.save_inward("AP 39 UA 4521", "Residential", "Mixed", 7000, "Op")
    c = CloudSync(d, s)
    c._get_bucket = lambda cfg: Bucket()
    c.run_once()
    assert c.state == "synced" and d.queue_waiting() == []
    assert any(k.startswith("Lions_Group/ISWM_Donthali/") and "/entries/INR" in k for k in uploaded)


def test_admin_requires_pin_and_updates_operators(tmp_path, monkeypatch):
    monkeypatch.setenv("ISWM_DATA_DIR", str(tmp_path))
    svc = Service(Settings(str(tmp_path / "s.json")), DB(str(tmp_path / "d.sqlite3")), start_devices=False)
    with pytest.raises(RuleError):
        svc.admin_save({"site_name": "X"})
    with pytest.raises(RuleError):
        svc.admin_login("1234")
    svc.admin_login("0000")
    svc.admin_save({"site_name": "ISWM Test", "admin_pin_hash": "ignored"},
                   operators=[{"name": "Ramesh K.", "pin": "4821"}], adminPin="9999")
    assert svc.boot()["site"] == "ISWM Test" and svc.boot()["operators"] == ["Ramesh K."]
    assert svc.settings.check_admin("9999") and not svc.settings.check_admin("0000")
    with pytest.raises(RuleError):
        svc.login("Ramesh K.", "0000")
    svc.login("Ramesh K.", "4821")

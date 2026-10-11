import datetime as dt
import json
import os
import time

import pytest

from iswm.db import DB, RuleError, shift_index, ticket_in, ticket_out, yymm
from iswm.service import Service
from iswm.settings import Settings, camera_urls, check_pin, hash_pin, password_problem, pin_problem
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


def test_pins_and_passwords():
    assert not check_pin("0000", "")  # no default PIN any more
    stored = hash_pin("4821")
    assert check_pin("4821", stored) and not check_pin("0000", stored)
    assert pin_problem("1111") and pin_problem("12a4") and not pin_problem("4821")
    assert password_problem("0000") and password_problem("abcdefgh") and password_problem("password1"[:8])
    assert password_problem("Plant4821x", ["4821"])
    assert password_problem("Donthali2026") is None


def test_camera_urls_quote_passwords():
    cfg = {"type": "RTSP", "ip": "192.168.1.64", "port": "554", "username": "admin", "password": "p@ss:w/rd#1",
           "endpoint": "/Streaming/Channels/101", "snapshot_endpoint": "/ISAPI/Streaming/channels/101/picture",
           "http_port": "80"}
    stream, snap = camera_urls(cfg)
    assert stream == "rtsp://admin:p%40ss%3Aw%2Frd%231@192.168.1.64:554/Streaming/Channels/101"
    assert snap == "http://192.168.1.64:80/ISAPI/Streaming/channels/101/picture"
    assert camera_urls({"type": "USB"}) == ("", "")


def _setup(svc):
    svc.setup("ISWM Test", "Lions Group", "Donthali2026", "Operator 1", "4821")


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
    _setup(svc)
    svc.login("Operator 1", "4821")
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


class FakeSession:
    def __init__(self, fail=False):
        self.posts, self.fail = [], fail

    def post(self, url, data=None, headers=None, timeout=None):
        if self.fail:
            raise ConnectionError("no internet")
        self.posts.append((url, data))

        class R:
            status_code, text = 200, "{}"
        return R()


def test_cloud_sync_batches_records_into_one_request(tmp_path):
    from iswm.cloud import CloudSync

    key = tmp_path / "key.json"
    key.write_text("{}")
    s = Settings(str(tmp_path / "s.json"))
    s.update({"cloud": {"enabled": True, "credentials_path": str(key), "sync_minutes": 10}})
    d = DB(str(tmp_path / "d.sqlite3"))
    c = CloudSync(d, s)
    fake = FakeSession()
    c._auth = lambda cfg: (setattr(c, "_project", "proj"), fake)[1]
    c.run_once()
    assert fake.posts == [] and c.state == "synced"  # nothing new: no internet used
    d.save_tare("AP 39 UA 4521", 5000, "Op")
    d.save_inward("AP 39 UA 4521", "Residential", "Mixed", 8000, "Op")
    d.save_inward("AP 21 TD 0418", "Commercial", "Dry", 4000, "Op")
    c.run_once()
    assert len(fake.posts) == 1 and d.queue_waiting() == []  # three records, one request
    url, body = fake.posts[0]
    assert url.endswith("projects/proj/databases/(default)/documents:commit")
    names = [w["update"]["name"] for w in json.loads(body)["writes"]]
    assert any(n.endswith("sites/iswm-donthali/entries/INR" + yymm() + "0001") for n in names)
    assert any("/vehicles/AP39UA4521" in n for n in names) and not any("upload" in u for u, _ in fake.posts)
    entry = next(w for w in json.loads(body)["writes"] if "/entries/" in w["update"]["name"])["update"]["fields"]
    assert entry["net_kg"] == {"integerValue": "3000"} and "timestampValue" in entry["created_at"]
    assert "front_photo" not in entry  # photos stay on the PC unless chosen
    # offline: nothing lost, and the wait grows
    c2 = CloudSync(d, s)
    c2._auth = lambda cfg: (setattr(c2, "_project", "proj"), FakeSession(fail=True))[1]
    d.ask_correction("INR" + yymm() + "0001", "check", "Op")
    c2.run_once()
    assert c2.state == "offline" and c2._backoff == 2 and len(d.queue_waiting()) == 1


def test_camera_runs_only_on_demand(tmp_path):
    import http.server
    import threading
    import cv2
    import numpy as np

    ok, jpg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            self.wfile.write(jpg.tobytes())

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from iswm.cameras import Camera
    cam = Camera("front", {"type": "HTTP", "ip": "127.0.0.1", "port": str(srv.server_address[1]), "endpoint": "/x.jpg"})
    cam.start()
    try:
        time.sleep(2.5)
        assert hits == [] and not cam.live()  # nobody asked: the camera is not contacted at all
        assert cam.photo(wait=6) is not None  # Save asks: it starts, takes the picture
        n = len(hits)
        assert n > 0
        cam._want_until = 0  # demand ends
        time.sleep(2.5)
        m = len(hits)
        time.sleep(1.5)
        assert len(hits) == m and not cam.live()  # and stops again
    finally:
        cam.stop()
        srv.shutdown()


def test_setup_admin_and_logo(tmp_path, monkeypatch):
    import base64
    monkeypatch.setenv("ISWM_DATA_DIR", str(tmp_path))
    svc = Service(Settings(str(tmp_path / "s.json")), DB(str(tmp_path / "d.sqlite3")), start_devices=False)
    assert svc.boot()["needsSetup"] and svc.boot()["operators"] == []
    with pytest.raises(RuleError):
        svc.setup("Site", "Co", "short", "Op", "4821")  # weak password
    with pytest.raises(RuleError):
        svc.setup("Site", "Co", "Plant4821x", "Op", "4821")  # contains operator PIN
    _setup(svc)
    assert not svc.boot()["needsSetup"]
    with pytest.raises(RuleError):
        _setup(svc)  # setup cannot run twice (would let anyone reset the admin password)
    with pytest.raises(RuleError):
        svc.admin_save({"site_name": "X"})  # locked
    with pytest.raises(RuleError):
        svc.admin_login("0000")
    svc.admin_login("Donthali2026")
    assert svc.live()["admin"]
    svc.admin_save({"site_name": "ISWM Test 2", "admin_password_hash": "ignored"},
                   operators=[{"name": "Operator 1", "pin": ""}, {"name": "Ramesh K.", "pin": "5932"}],
                   adminPassword="NewPass2027")
    assert svc.boot()["site"] == "ISWM Test 2" and svc.boot()["operators"] == ["Operator 1", "Ramesh K."]
    assert svc.settings.check_admin("NewPass2027") and not svc.settings.check_admin("Donthali2026")
    with pytest.raises(RuleError):  # same PIN as Operator 1
        svc.admin_save({}, operators=[{"name": "Operator 1", "pin": ""}, {"name": "Ramesh K.", "pin": "4821"}])
    with pytest.raises(RuleError):  # new operator without PIN
        svc.admin_save({}, operators=[{"name": "Operator 1", "pin": ""}, {"name": "New", "pin": ""}])
    with pytest.raises(RuleError):
        svc.admin_set_logo("data:image/png;base64," + base64.b64encode(b"not an image").decode())
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    assert svc.admin_set_logo("data:image/png;base64," + base64.b64encode(png).decode())["logo"]
    assert svc.logo_path().endswith("logo.png") and svc.boot()["logo"]
    svc.admin_lock()
    with pytest.raises(RuleError):
        svc.admin_clear_logo()
    svc.login("Ramesh K.", "5932")
    for _ in range(5):
        with pytest.raises(RuleError):
            svc.admin_login("wrong-pass1")
    with pytest.raises(RuleError, match="Wait"):
        svc.admin_login("NewPass2027")  # locked out after 5 wrong tries


def test_admin_fix_entry_and_rename_vehicle(db):
    db.save_tare("AP 39 UA 4521", 5000, "Op")
    e = db.save_inward("AP 39 UA 4251", "Residential", "Mixed", 8000, "Op")  # typo: pending, unknown vehicle
    assert e["net_kg"] is None
    db.ask_correction(e["id"], "Wrong vehicle number", "Op")
    with pytest.raises(RuleError):
        db.fix_entry(e["id"], {"vno": "AP 39 UA 4521"}, "")  # reason needed
    f = db.fix_entry(e["id"], {"vno": "AP 39 UA 4521", "waste_type": "Wet"}, "typo")
    assert f["vno"] == "AP 39 UA 4521" and f["net_kg"] == 3000 and f["waste_type"] == "Wet" and f["id"] == e["id"]
    assert {x["field"] for x in db.edits(e["id"])} == {"vno", "waste_type"}
    assert db.trips(dt.date.today(), dt.date.today(), status="Asked") == []
    # rename merges a mistyped vehicle into the right one, completing its trips
    g = db.save_inward("AP39UA452", "Commercial", "Dry", 7000, "Op")
    r = db.rename_vehicle("AP39UA452", "AP 39 UA 4521", "typo")
    assert r["trips"] == 1 and db.entry(g["id"])["net_kg"] == 2000 and db.vehicle("AP39UA452") is None
    found = db.trips(dt.date.today(), dt.date.today(), query="ua4521")
    assert len(found) == 2 and all(t["vno"] == "AP 39 UA 4521" for t in found)
    assert db.report_custom("Vehicle", dt.date.today(), dt.date.today(), "Both")[0]["trips"] == 2


def test_settings_survive_damage(tmp_path):
    d = DB(str(tmp_path / "d.sqlite3"))
    path = str(tmp_path / "settings.json")
    s = Settings(path, store=d)
    s.update({"site_name": "Plant A"})
    s.update({"site_name": "Plant B"})
    open(path, "w").write("")  # power cut left an empty file
    s2 = Settings(path, store=d)
    assert s2.recovered == "database" and s2.get("site_name") == "Plant B"
    assert any(n.startswith("settings.json.broken-") for n in os.listdir(tmp_path))
    open(path, "w").write("{garbage")
    s3 = Settings(path)  # no database copy available: falls back to settings.json.bak
    assert s3.recovered == "backup" and s3.get("site_name") == "Plant B"


def test_maintenance_removes_only_old_and_sent_photos(tmp_path, monkeypatch):
    monkeypatch.setenv("ISWM_DATA_DIR", str(tmp_path))
    svc = Service(Settings(str(tmp_path / "s.json")), DB(str(tmp_path / "d.sqlite3")), start_devices=False)
    img = tmp_path / "images"
    old, new = (dt.date.today() - dt.timedelta(days=200)).isoformat(), dt.date.today().isoformat()
    for day in (old, new):
        (img / day).mkdir(parents=True)
        (img / day / "x.jpg").write_bytes(b"x")
    rep = svc.maint.run()
    assert rep["removed_photo_days"] == 1 and not (img / old).exists() and (img / new).exists()
    assert os.path.exists(rep["backup"])
    st = svc.maint.storage()
    assert st["disk_free_gb"] > 0


def test_live_view_needs_password(tmp_path, monkeypatch):
    import base64
    import urllib.error
    import urllib.request
    monkeypatch.setenv("ISWM_DATA_DIR", str(tmp_path))
    svc = Service(Settings(str(tmp_path / "s.json")), DB(str(tmp_path / "d.sqlite3")), start_devices=False)
    _setup(svc)
    svc.admin_login("Donthali2026")
    with pytest.raises(RuleError):
        svc.admin_save({"live_view": {"enabled": True, "port": 18095}}, liveViewPassword="Donthali2026")
    svc.admin_save({"live_view": {"enabled": True, "port": 18095}}, liveViewPassword="watch123")
    try:
        assert svc.liveview.running()
        url = "http://127.0.0.1:18095/api/today"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url, timeout=3)
        req = urllib.request.Request(url, headers={"Authorization": "Basic " + base64.b64encode(b"viewer:watch123").decode()})
        body = json.loads(urllib.request.urlopen(req, timeout=3).read())
        assert body["in"]["trips"] == 0 and body["rows"] == []
        assert "password_hash" not in svc.settings.public()["live_view"]
    finally:
        svc.liveview.stop()

"""The shared API, against a tiny in-memory stand-in for Firestore."""
import datetime as dt
import importlib.util
import os

import pytest

flask = pytest.importorskip("flask")
spec = importlib.util.spec_from_file_location("cloud_api_main", os.path.join(os.path.dirname(__file__), "..", "cloud_api", "main.py"))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
TZ = api.TZ


class Doc:
    def __init__(self, id, data):
        self.id, self._d = id, data

    def to_dict(self):
        return dict(self._d)


class Coll:
    def __init__(self, store, path):
        self.store, self.path, self.filters = store, path, []

    def document(self, id):
        return Coll(self.store, self.path + "/" + id)

    def collection(self, name):
        return Coll(self.store, self.path + "/" + name)

    def where(self, f, op, v):
        c = Coll(self.store, self.path)
        c.filters = self.filters + [(f, op, v)]
        return c

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def stream(self):
        ops = {">=": lambda a, b: a >= b, "<": lambda a, b: a < b}
        for path, data in self.store.items():
            parent, _, id = path.rpartition("/")
            if parent == self.path and all(f in data and ops[o](data[f], v) for f, o, v in self.filters):
                yield Doc(id, data)


class FakeDB:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        return Coll(self.store, name)


@pytest.fixture
def client(monkeypatch):
    now = dt.datetime.now(TZ)
    store = {
        "sites/iswm-donthali": {"name": "ISWM Donthali"},
        "sites/iswm-kadiri": {"name": "ISWM Kadiri"},
        "sites/iswm-donthali/entries/INR26100001": {"id": "INR26100001", "dir": "in", "vno": "AP 39 UA 4521",
                                                    "waste_type": "Mixed", "net_kg": 3000, "created_at": now},
        "sites/iswm-donthali/entries/INC26100002": {"id": "INC26100002", "dir": "in", "vno": "AP 21 TD 0418",
                                                    "waste_type": "Dry", "net_kg": None, "created_at": now},
    }
    monkeypatch.setattr(api, "_db", FakeDB(store))
    monkeypatch.setenv("API_KEYS", "office:secret1,kadiri:secret2@iswm-kadiri")
    return api.app.test_client()


def test_api_keys_and_site_limits(client):
    assert client.get("/v1/sites").status_code == 401
    assert len(client.get("/v1/sites", headers={"X-API-Key": "secret1"}).get_json()) == 2
    assert [s["id"] for s in client.get("/v1/sites", headers={"X-API-Key": "secret2"}).get_json()] == ["iswm-kadiri"]
    assert client.get("/v1/sites/iswm-donthali/entries", headers={"X-API-Key": "secret2"}).status_code == 404


def test_entries_and_summary(client):
    h = {"X-API-Key": "secret1"}
    rows = client.get("/v1/sites/iswm-donthali/entries?vehicle=ap39", headers=h).get_json()
    assert [r["id"] for r in rows] == ["INR26100001"]
    s = client.get("/v1/sites/iswm-donthali/summary", headers=h).get_json()
    assert s["in"]["Mixed"] == {"trips": 1, "net_kg": 3000} and s["incomplete"] == 1


def test_remote_view_end_to_end(tmp_path, monkeypatch):
    """Plant <-> relay <-> viewer over real HTTP: pictures flow only while someone watches."""
    import http.server
    import threading
    import time
    import cv2
    import numpy as np
    import requests
    from werkzeug.serving import make_server
    from iswm.db import DB
    from iswm.service import Service
    from iswm.settings import Settings

    monkeypatch.setenv("API_KEYS", "boss:viewkey")
    monkeypatch.setenv("PLANT_KEYS", "iswm-donthali:plantkey")
    monkeypatch.setenv("ISWM_DATA_DIR", str(tmp_path))
    api.LIVE.clear()
    relay = make_server("127.0.0.1", 0, api.app, threaded=True)
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    relay_url = "http://127.0.0.1:%d" % relay.server_port

    jpg = cv2.imencode(".jpg", np.full((720, 1280, 3), 90, np.uint8))[1].tobytes()
    hits = []

    class Cam(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(1)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            self.wfile.write(jpg)

    camsrv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Cam)
    threading.Thread(target=camsrv.serve_forever, daemon=True).start()
    s = Settings(str(tmp_path / "s.json"))
    cam = {"type": "HTTP", "ip": "127.0.0.1", "port": str(camsrv.server_address[1]), "endpoint": "/x.jpg"}
    s.update({"cameras": {"front": {**cam, "label": "Front cam"}, "back": {"type": "None", "label": "Back cam"},
                          "cam3": {**cam, "label": "Tipping floor"}},
              "remote": {"enabled": True, "relay_url": relay_url, "site_key": "plantkey", "poll_seconds": 10}})
    svc = Service(s, DB(str(tmp_path / "d.sqlite3")), start_devices=False)
    svc.cams.start()
    t = threading.Thread(target=svc.remote._loop, daemon=True)
    t.start()
    try:
        time.sleep(2)
        assert svc.remote.state == "waiting" and hits == []  # nobody watching: camera untouched, nothing sent
        sent_before = svc.remote.bytes
        state_url = relay_url + "/v1/sites/iswm-donthali/live/state"
        state = requests.get(state_url, headers={"X-API-Key": "viewkey"}).json()
        # the names the admin gave the cameras reach the remote page
        assert state["cams"] == [["front", "Front cam"], ["back", "Back cam"], ["cam3", "Tipping floor"]]
        r = requests.get(relay_url + "/v1/sites/iswm-donthali/live/cam3.mjpg?key=viewkey&q=low", stream=True, timeout=40)
        frames = r.iter_content(4096)
        buf = b""
        for chunk in frames:
            buf += chunk
            if buf.count(b"--frame") >= 2:
                break
        assert b"Content-Type: image/jpeg" in buf and svc.remote.bytes > sent_before
        # renamed while someone watches: the new name arrives with the next picture
        c = svc.settings.get("cameras")
        c["cam3"]["label"] = "Windrow yard"
        svc.settings.replace("cameras", c)
        svc.cams.configure(c)
        deadline = time.time() + 15
        while time.time() < deadline:
            next(frames)
            state = requests.get(state_url, headers={"X-API-Key": "viewkey"}).json()
            if ["cam3", "Windrow yard"] in state["cams"]:
                break
        r.close()
        assert ["cam3", "Windrow yard"] in state["cams"]
        assert state["plant_online"] and state["weight"] is not None
        # newest single picture, answered at once (what dashboards use)
        jpg_url = relay_url + "/v1/sites/iswm-donthali/live/cam3.jpg"
        deadline = time.time() + 20
        while time.time() < deadline:
            one = requests.get(jpg_url, headers={"X-API-Key": "viewkey"}, timeout=10)
            if one.status_code == 200:
                break
            time.sleep(0.5)
        assert one.status_code == 200 and one.content.startswith(b"\xff\xd8")
        assert requests.get(jpg_url).status_code == 401
        page = requests.get(relay_url + "/live/iswm-donthali?key=viewkey").text
        assert "buttons(s.cams)" in page
        assert requests.get(relay_url + "/v1/plant/iswm-donthali/wanted", headers={"X-Site-Key": "bad"}).status_code == 401
        deadline = time.time() + 30
        while svc.remote.state == "sending" and time.time() < deadline:
            time.sleep(0.5)
        assert svc.remote.state == "waiting"  # viewer left: plant stopped sending
        b = svc.remote.bytes
        time.sleep(3)
        assert svc.remote.bytes == b
    finally:
        svc.remote.stop()
        svc.cams.stop()
        relay.shutdown()
        camsrv.shutdown()

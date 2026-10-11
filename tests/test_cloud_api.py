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

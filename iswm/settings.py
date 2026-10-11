"""Site settings, stored as settings.json in the data folder.

Camera and weighbridge field names follow adex_lite's settings_storage.py so
a technician sees the same options (IP, port, user, password, endpoint).

Nothing works until the first-run setup has created an admin password and
at least one operator: there are no default PINs or passwords.
"""
import copy
import hashlib
import json
import os
import re
import secrets
import threading
import urllib.parse

from . import paths


def camera_defaults(index):
    return {
        "type": "USB",            # USB | RTSP | HTTP | None
        "brand": "Hikvision",     # preset that fills in endpoints: Hikvision | Dahua | CP Plus | Generic
        "index": index,           # USB device number
        "ip": "", "port": "554", "username": "", "password": "",
        "endpoint": "/Streaming/Channels/101",   # RTSP stream path, or HTTP MJPEG/JPEG path
        "snapshot_endpoint": "",  # optional: camera's own full-resolution JPEG, used for saved photos
        "http_port": "80",        # port for the snapshot endpoint (RTSP cameras)
        "url": "",                # optional: full URL typed by hand; wins over the fields above
    }


# Endpoints for the main (highest quality) stream and full-resolution snapshot.
BRANDS = {
    "Hikvision": {"rtsp": "/Streaming/Channels/101", "snapshot": "/ISAPI/Streaming/channels/101/picture"},
    "Dahua": {"rtsp": "/cam/realmonitor?channel=1&subtype=0", "snapshot": "/cgi-bin/snapshot.cgi?channel=1"},
    "CP Plus": {"rtsp": "/cam/realmonitor?channel=1&subtype=0", "snapshot": "/cgi-bin/snapshot.cgi?channel=1"},
    "Generic": {"rtsp": "/stream1", "snapshot": ""},
}

DEFAULTS = {
    "site_name": "ISWM Donthali",
    "agency_name": "Lions Group",
    "admin_password_hash": "",
    "operators": [],
    "weighbridge": {
        "simulate": True,
        "com_port": "",
        "baud_rate": 9600,
        "data_bits": 8,
        "parity": "None",
        "stop_bits": 1.0,
        "regex_pattern": r"(\d+\.?\d*)",
        "weight_multiplier": 1.0,
        "stable_tolerance_kg": 10,
        "stable_seconds": 2.0,
        "min_weight_kg": 10,
    },
    "cameras": {"front": camera_defaults(0), "back": camera_defaults(1)},
    "cloud": {"enabled": False, "bucket_name": "", "credentials_path": ""},
    "shifts": {"count": 3, "starts": ["06:00", "14:00", "22:00"]},
    "reports_folder": "",
    "outward_destinations": ["Ultratech cement", "Sri Sai traders", "Farmer buyer", "Landfill cell 2"],
}

ADMIN_ITERATIONS = 200_000


def hash_pin(pin, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256((salt + ":" + str(pin)).encode()).hexdigest()
    return salt + "$" + digest


def check_pin(pin, stored):
    if not stored:
        return False
    salt, _, _ = stored.partition("$")
    return secrets.compare_digest(hash_pin(pin, salt), stored)


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(pw).encode(), salt.encode(), ADMIN_ITERATIONS).hex()
    return "pbkdf2$" + salt + "$" + digest


def check_password(pw, stored):
    if not stored or not stored.startswith("pbkdf2$"):
        return False
    _, salt, _ = stored.split("$", 2)
    return secrets.compare_digest(hash_password(pw, salt), stored)


WEAK = {"password", "admin123", "12345678", "123456", "qwerty", "iswm1234", "admin@123"}


def password_problem(pw, operator_pins=()):
    """Why an admin password is not acceptable, or None. Plain words; shown on screen."""
    pw = pw or ""
    if len(pw) < 8:
        return "Admin password needs at least 8 characters."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Admin password needs both letters and numbers."
    if pw.lower() in WEAK or len(set(pw)) < 4:
        return "That admin password is too easy to guess."
    if any(p and p in pw for p in operator_pins):
        return "Admin password must not contain an operator's PIN."
    return None


def pin_problem(pin):
    pin = str(pin or "")
    if not (pin.isdigit() and len(pin) == 4):
        return "PIN must be 4 numbers."
    if len(set(pin)) == 1 or pin in ("1234", "4321", "0123"):
        return "That PIN is too easy to guess."
    return None


def camera_urls(cfg):
    """(stream_url, snapshot_url) for an RTSP or HTTP camera.

    User name and password are URL-quoted, so passwords with @ : / # work
    (adex_lite pasted them in raw, which breaks those passwords).
    """
    kind = (cfg.get("type") or "USB").upper()
    if cfg.get("url"):
        return cfg["url"], snapshot_url(cfg)
    ip = (cfg.get("ip") or "").strip()
    if not ip or kind not in ("RTSP", "HTTP"):
        return "", ""
    user, pw = cfg.get("username") or "", cfg.get("password") or ""
    auth = (urllib.parse.quote(user, safe="") + ":" + urllib.parse.quote(pw, safe="") + "@") if user else ""
    ep = cfg.get("endpoint") or ""
    if ep and not ep.startswith("/"):
        ep = "/" + ep
    scheme = "rtsp" if kind == "RTSP" else "http"
    port = str(cfg.get("port") or ("554" if kind == "RTSP" else "80"))
    return "%s://%s%s:%s%s" % (scheme, auth, ip, port, ep), snapshot_url(cfg)


def snapshot_url(cfg):
    """Snapshot URL without credentials (sent separately, with digest auth)."""
    ip, ep = (cfg.get("ip") or "").strip(), (cfg.get("snapshot_endpoint") or "").strip()
    if not ip or not ep:
        return ""
    if not ep.startswith("/"):
        ep = "/" + ep
    kind = (cfg.get("type") or "").upper()
    port = str(cfg.get("port") if kind == "HTTP" else cfg.get("http_port") or "80")
    return "http://%s:%s%s" % (ip, port, ep)


def _merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(paths.data_dir(), "settings.json")
        self._lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            data = copy.deepcopy(DEFAULTS)
            self._write(data)
            return data
        raw.pop("admin_pin_hash", None)  # the old 4-number admin PIN is not accepted any more
        raw["operators"] = [o for o in raw.get("operators", []) if o.get("pin_hash")]
        return _merge(DEFAULTS, raw)

    def _write(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def update(self, patch):
        with self._lock:
            self.data = _merge(self.data, patch)
            self._write(self.data)

    def replace(self, key, value):
        with self._lock:
            self.data[key] = value
            self._write(self.data)

    def needs_setup(self):
        return not self.data.get("admin_password_hash") or not self.data.get("operators")

    # operators -------------------------------------------------------
    def operator_names(self):
        return [o["name"] for o in self.data.get("operators", [])]

    def check_operator(self, name, pin):
        for op in self.data.get("operators", []):
            if op["name"] == name:
                return check_pin(pin, op.get("pin_hash", ""))
        return False

    def operator_pin_matches(self, pw):
        """True if any operator's PIN appears inside ``pw``."""
        for op in self.data.get("operators", []):
            stored = op.get("pin_hash", "")
            for i in range(max(0, len(pw) - 3)):
                if check_pin(pw[i:i + 4], stored):
                    return True
        return False

    def check_admin(self, pw):
        return check_password(pw, self.data.get("admin_password_hash", ""))

    def public(self):
        """Settings for the admin screen, without password or PIN hashes."""
        d = copy.deepcopy(self.data)
        d.pop("admin_password_hash", None)
        d["operators"] = [{"name": o["name"], "has_pin": bool(o.get("pin_hash"))} for o in d.get("operators", [])]
        return d

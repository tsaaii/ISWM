"""Site settings, stored as settings.json in the data folder.

Field names for the weighbridge and cameras follow adex_lite's
settings_storage.py so a technician sees the same options.
"""
import copy
import hashlib
import json
import os
import secrets
import threading

from . import paths

DEFAULTS = {
    "site_name": "ISWM Donthali",
    "agency_name": "Lions Group",
    "admin_pin_hash": "",  # empty means the default admin PIN 0000 is active
    "operators": [
        {"name": "Operator 1", "pin_hash": ""},
    ],
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
    "cameras": {
        "front": {"type": "USB", "index": 0, "url": ""},
        "back": {"type": "USB", "index": 1, "url": ""},
    },
    "cloud": {
        "enabled": False,
        "bucket_name": "",
        "credentials_path": "",
    },
    "shifts": {"count": 3, "starts": ["06:00", "14:00", "22:00"]},
    "reports_folder": "",
    "outward_destinations": ["Ultratech cement", "Sri Sai traders", "Farmer buyer", "Landfill cell 2"],
}

DEFAULT_PIN = "0000"


def hash_pin(pin, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256((salt + ":" + str(pin)).encode()).hexdigest()
    return salt + "$" + digest


def check_pin(pin, stored):
    if not stored:
        return str(pin) == DEFAULT_PIN
    salt, _, _ = stored.partition("$")
    return secrets.compare_digest(hash_pin(pin, salt), stored)


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
                return _merge(DEFAULTS, json.load(f))
        except (OSError, ValueError):
            data = copy.deepcopy(DEFAULTS)
            self._write(data)
            return data

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

    # operators -------------------------------------------------------
    def operator_names(self):
        return [o["name"] for o in self.data.get("operators", [])]

    def check_operator(self, name, pin):
        for op in self.data.get("operators", []):
            if op["name"] == name:
                return check_pin(pin, op.get("pin_hash", ""))
        return False

    def check_admin(self, pin):
        return check_pin(pin, self.data.get("admin_pin_hash", ""))

    def using_default_pins(self):
        return not self.data.get("admin_pin_hash") or any(
            not o.get("pin_hash") for o in self.data.get("operators", []))

    def public(self):
        """Settings for the admin screen, without PIN hashes."""
        d = copy.deepcopy(self.data)
        d.pop("admin_pin_hash", None)
        d["operators"] = [{"name": o["name"], "has_pin": bool(o.get("pin_hash"))} for o in d.get("operators", [])]
        return d

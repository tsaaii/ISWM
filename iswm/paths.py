"""Where the app finds its bundled files and keeps its data.

Bundled files (web/) live inside the PyInstaller bundle when frozen.
Data (database, photos, settings, reports) lives in a folder next to the
.exe, like adex_lite's ``data`` folder, so a site can back it up by copying
one folder. ISWM_DATA_DIR overrides it (used by tests).
"""
import os
import sys


def is_frozen():
    return getattr(sys, "frozen", False)


def resource_dir():
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def web_dir():
    return os.path.join(resource_dir(), "web")


def data_dir():
    override = os.environ.get("ISWM_DATA_DIR")
    if override:
        path = override
    elif is_frozen():
        path = os.path.join(os.path.dirname(sys.executable), "ISWM_data")
    else:
        path = os.path.join(resource_dir(), "ISWM_data")
    os.makedirs(path, exist_ok=True)
    return path


def sub(*parts):
    path = os.path.join(data_dir(), *parts)
    os.makedirs(path, exist_ok=True)
    return path

"""Where the app finds its bundled files and keeps its data.

Bundled files (web/) live inside the PyInstaller bundle when frozen.
Data (database, photos, settings, reports) lives in one folder, so a site
backs up by copying that folder:

  * installed with ISWM-Setup.exe: C:\\ProgramData\\ISWM (Program Files is
    read-only, and ProgramData is shared by every Windows user on the PC);
  * unzipped copy: an ``ISWM_data`` folder next to ISWM.exe, if that folder
    exists or the .exe's folder is writable and not under Program Files;
  * ISWM_DATA_DIR overrides both (used by tests).
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
        exe_dir = os.path.dirname(sys.executable)
        portable = os.path.join(exe_dir, "ISWM_data")
        installed = os.path.exists(os.path.join(exe_dir, "installed.txt"))
        if os.path.isdir(portable) or (not installed and os.access(exe_dir, os.W_OK)):
            path = portable
        else:
            path = os.path.join(os.environ.get("PROGRAMDATA") or os.path.expanduser("~"), "ISWM")
    else:
        path = os.path.join(resource_dir(), "ISWM_data")
    os.makedirs(path, exist_ok=True)
    return path


def sub(*parts):
    path = os.path.join(data_dir(), *parts)
    os.makedirs(path, exist_ok=True)
    return path

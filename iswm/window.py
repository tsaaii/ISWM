"""Open the app window.

The screens open in Microsoft Edge's app mode: a plain window with the site
name in the title bar, no address bar or tabs. Edge is part of Windows 10
and 11, so nothing extra is installed, and nothing depends on .NET.

(The first versions used pywebview, which needs .NET through pythonnet. On
some PCs .NET refused to load it: "Failed to resolve
Python.Runtime.Loader.Initialize". Edge app mode avoids that whole layer.)

The window uses its own Edge profile in the data folder, so it is separate
from the person's normal browsing, opens with no sign-in or welcome pages,
and its process ends when the window is closed, which also stops ISWM.
If neither Edge nor Chrome is found, the default browser is used.
"""
import ctypes
import json
import logging
import os
import subprocess
import sys
import time
import webbrowser

from . import paths

EDGE_ARGS = ["--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
             "--hide-crash-restore-bubble", "--disable-translate", "--overscroll-history-navigation=0",
             "--disable-pinch", "--disable-features=Translate,msEdgeSidebarV2,msImplicitSignin,"
             "msEdgeWelcomePage,msShowFirstRunExperience,EdgeCollections", "--window-size=1400,760"]


def find_browser():
    names = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
    roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for n in names:
        for r in roots:
            if r and os.path.isfile(os.path.join(r, n)):
                return os.path.join(r, n)
    return None


def message(text, title="ISWM"):
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
            return
        except Exception:
            pass
    print(text, flush=True)


def _clean_profile(profile):
    """Mark the last session as closed normally, so Edge never shows 'Restore pages?'."""
    pref = os.path.join(profile, "Default", "Preferences")
    try:
        with open(pref, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("profile", {}).update({"exit_type": "Normal", "exited_cleanly": True})
        with open(pref, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except (OSError, ValueError):
        pass


def browser_command(browser, url):
    profile = paths.sub("browser-window")
    _clean_profile(profile)
    return [browser, "--app=" + url, "--user-data-dir=" + profile] + EDGE_ARGS


def run(service, url):
    """Show the app. Returns when the window is closed."""
    service.window = None
    browser = find_browser()
    if browser:
        logging.info("opening window with %s", browser)
        started = time.monotonic()
        proc = subprocess.Popen(browser_command(browser, url))
        proc.wait()  # with its own profile this process lives until the window is closed
        if time.monotonic() - started > 3:
            return
        logging.warning("browser window closed at once (code %s); using the default browser", proc.returncode)
    webbrowser.open(url)
    message("ISWM is open in your web browser.\n\nKeep this box open while you work. "
            "Close it to stop ISWM.\n\nIf the page did not open, paste this address into a browser:\n" + url)


def self_check():
    """Used by the build: is there a browser to show the window with?"""
    b = find_browser()
    logging.info("window check: %s", b or "no Edge or Chrome found")
    return bool(b)


class SingleInstance:
    """Only one ISWM per PC: a second start just says it is already open."""

    def __init__(self):
        self.path = os.path.join(paths.data_dir(), "iswm.lock")
        self.f = None

    def acquire(self):
        self.f = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.f.close()
            self.f = None
            return False

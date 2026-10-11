"""Open the app window, and never fail to show the screens.

1. Files unzipped from a download carry Windows' "came from the internet" mark
   (a Zone.Identifier stream). .NET then refuses to load pythonnet's
   Python.Runtime.dll and pywebview fails with "Failed to resolve
   Python.Runtime.Loader.Initialize". We remove that mark from our own files
   before opening the window.
2. If the pywebview window still cannot open (no .NET, broken WebView2, ...),
   the same screens open in Microsoft Edge's app mode: a plain window with no
   address bar, using its own profile so it closes cleanly with the app.
"""
import ctypes
import logging
import os
import subprocess
import sys
import time

from . import paths


def unblock_own_files():
    """Remove the downloaded-from-internet mark from the app's files (Windows only)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return 0
    removed = 0
    for root, _, files in os.walk(paths.resource_dir()):
        for f in files:
            try:
                os.remove(os.path.join(root, f) + ":Zone.Identifier")
                removed += 1
            except OSError:
                pass
    if removed:
        logging.info("removed the internet mark from %d files", removed)
    return removed


def find_edge():
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


def open_in_edge(url, title):
    edge = find_edge()
    if not edge:
        return False
    profile = paths.sub("browser-window")
    args = [edge, "--app=" + url, "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate,msEdgeSidebarV2", "--window-size=1400,760"]
    logging.info("opening in Edge app mode")
    proc = subprocess.Popen(args)
    proc.wait()  # with its own profile, this process lives until the window is closed
    return True


def self_check():
    """Load the same parts the window needs (pythonnet + WebView2 support) and log the result."""
    unblock_own_files()
    try:
        import clr  # noqa: F401  loads Python.Runtime.dll through .NET
        if sys.platform == "win32":
            from webview.platforms import winforms  # noqa: F401
        logging.info("window check ok")
        return True
    except Exception:
        logging.exception("window check failed")
        return False


def run(service, url):
    """Show the app. Returns when the window is closed."""
    title = service.settings.get("site_name") or "ISWM"
    unblock_own_files()
    try:
        import webview
        window = webview.create_window(title, url, width=1400, height=720, min_size=(1000, 560),
                                       background_color="#F2FBF4", text_select=False)
        service.window = window
        webview.start(private_mode=False)
        return
    except Exception:
        logging.exception("app window could not open; trying Edge app mode")
        service.window = None
    if open_in_edge(url, title):
        return
    message("ISWM is running, but its window could not open on this PC.\n\n"
            "Install Microsoft Edge WebView2 (or Microsoft Edge), or open this address in a browser:\n\n"
            + url + "\n\nClose this box to stop ISWM.")
    time.sleep(0.5)

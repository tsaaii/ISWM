"""Open the app window.

1. Standalone: a Qt WebEngine window that ships inside ISWM (its own built-in
   Chromium), so it needs neither Edge nor .NET, and looks like a normal
   program: plant icon, site name in the title bar, no address bar, no
   right-click menu, and it cannot be navigated away from the app.
2. If that cannot start (e.g. a very old graphics driver), Microsoft Edge's
   app mode is used: a plain window with no address bar.
3. Last resort: the default browser.

(Early versions used pywebview, which needs .NET through pythonnet; on some PCs
.NET refused to load it: "Failed to resolve Python.Runtime.Loader.Initialize".)
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


def run_qt(url, title, data_dir):
    """The standalone window. Returns False if Qt WebEngine is not available here."""
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QIcon
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication, QMainWindow
    except Exception:
        logging.exception("standalone window not available")
        return False
    if "--software" in sys.argv or os.environ.get("ISWM_SOFTWARE_GL"):
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu"
    origin = url.split("/index.html")[0]

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, target, kind, main_frame):
            return target.toString().startswith(origin)  # never leave the app

        def createWindow(self, kind):
            return None  # no pop-up windows

    app = QApplication.instance() or QApplication(sys.argv[:1])
    profile = QWebEngineProfile("iswm", app)  # keeps the keyboard setting and last operator between starts
    profile.setPersistentStoragePath(os.path.join(data_dir, "window-storage"))
    profile.setCachePath(os.path.join(data_dir, "window-cache"))
    view = QWebEngineView()
    page = Page(profile, view)
    view.setPage(page)
    view.setContextMenuPolicy(Qt.NoContextMenu)
    win = QMainWindow()
    win.setWindowTitle(title)
    icon = os.path.join(paths.web_dir(), "favicon.png")
    if os.path.exists(icon):
        win.setWindowIcon(QIcon(icon))
    win.setCentralWidget(view)
    win.setMinimumSize(1000, 560)
    win.resize(1400, 760)

    def fullscreen(req):
        req.accept()
        win.showFullScreen() if req.toggleOn() else win.showNormal()

    page.fullScreenRequested.connect(fullscreen)
    page.titleChanged.connect(lambda t: win.setWindowTitle(t or title))
    view.setUrl(QUrl(url))
    win.show()
    logging.info("standalone window open")
    app.exec()
    return True


def run(service, url):
    """Show the app. Returns when the window is closed."""
    service.window = None
    title = service.settings.get("site_name") or "ISWM"
    try:
        if run_qt(url, title, paths.data_dir()):
            return
    except Exception:
        logging.exception("standalone window failed; trying Edge")
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
    """Used by the build: open the standalone window off-screen and check a page really loads."""
    if sys.platform != "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv[:1])
        view = QWebEngineView()
        result = {}
        view.loadFinished.connect(lambda ok: (result.__setitem__("ok", ok), app.quit()))
        QTimer.singleShot(30000, app.quit)
        view.setHtml("<html><body>ISWM window check</body></html>", QUrl("http://127.0.0.1/"))
        app.exec()
        logging.info("window check: page loaded = %s", result.get("ok"))
        return bool(result.get("ok"))
    except Exception:
        logging.exception("window check failed")
        return False


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

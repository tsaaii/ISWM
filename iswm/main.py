"""Start the app: services, local server, then the window.

    ISWM.exe                 normal start, opens the app window
    ISWM.exe --browser       no window; prints a URL to open in a browser
                             (for testing on a PC without WebView2)
"""
import argparse
import logging
import logging.handlers
import os
import sys
import time

from . import paths


def _log_setup():
    # one log file per day, old ones removed by maintenance (and by the handler after 90 files)
    handler = logging.handlers.TimedRotatingFileHandler(os.path.join(paths.sub("logs"), "iswm.log"),
                                                        when="midnight", backupCount=90, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if getattr(sys, "frozen", False) and sys.stderr is None:  # windowed exe has no console
        sys.stdout = sys.stderr = open(os.path.join(paths.sub("logs"), "console.log"), "a", buffering=1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ISWM")
    ap.add_argument("--browser", action="store_true", help="run without a window; open the printed URL")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args(argv)
    _log_setup()

    from .server import serve
    from .service import Service

    service = Service()
    url, _, httpd = serve(service, port=args.port)
    logging.info("serving %s", url.split("#")[0])
    try:
        if args.browser:
            print("Open this address in a browser:\n  " + url, flush=True)
            while True:
                time.sleep(3600)
        else:
            import webview
            window = webview.create_window(service.settings.get("site_name") or "ISWM", url,
                                           width=1400, height=720, min_size=(1000, 560),
                                           background_color="#F2FBF4", text_select=False)
            service.window = window
            webview.start(private_mode=False)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        service.shutdown()


if __name__ == "__main__":
    main()

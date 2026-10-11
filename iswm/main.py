"""Start the app: services, local server, then the window.

    ISWM.exe                 normal start, opens the app window
    ISWM.exe --browser       no window; prints a URL to open in a browser
                             (for testing)
    ISWM.exe --check         check a browser is available for the window (used by the build)
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
    ap.add_argument("--version", action="store_true", help="show the version and exit")
    ap.add_argument("--check", action="store_true", help="check a browser is available for the window, log the result, exit")
    args = ap.parse_args(argv)
    if args.version:
        from . import __version__
        from .window import message
        message("ISWM version " + __version__ + "\nWindow: Edge app mode (no .NET)")
        return
    _log_setup()
    from . import __version__
    logging.info("ISWM %s starting", __version__)
    if args.check:
        from .window import self_check
        sys.exit(0 if self_check() else 1)

    from .window import SingleInstance, message
    lock = SingleInstance()
    if not lock.acquire():
        message("ISWM is already open on this computer.")
        return

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
            from .window import run
            run(service, url)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        service.shutdown()


if __name__ == "__main__":
    main()

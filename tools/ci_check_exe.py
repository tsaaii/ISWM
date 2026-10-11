"""Build check (Windows): the frozen ISWM.exe must start on a PC where every file
carries the 'downloaded from the internet' mark, like a zip unpacked from Downloads."""
import os
import subprocess
import sys
import time

root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "dist/ISWM")
exe = os.path.join(root, "ISWM.exe")
logs = os.path.join(root, "ISWM_data", "logs")


def tail(name, n=20):
    p = os.path.join(logs, name)
    if not os.path.exists(p):
        return ["(no %s)" % name]
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-n:]


def fail(why):
    print("::error::" + why)
    for name in ("iswm.log", "console.log"):
        for line in tail(name):
            print("::error::%s %s" % (name, line))
    sys.exit(1)


for bad in ("pythonnet", "webview", "clr_loader"):
    if os.path.exists(os.path.join(root, "_internal", bad)):
        fail("the build still contains %s (the .NET window that fails on some PCs)" % bad)

marked = 0
for d, _, files in os.walk(root):
    for f in files:
        try:
            with open(os.path.join(d, f) + ":Zone.Identifier", "w") as z:
                z.write("[ZoneTransfer]\r\nZoneId=3\r\n")
            marked += 1
        except OSError:
            pass
print("marked %d files as downloaded" % marked)

try:
    code = subprocess.run([exe, "--check"], timeout=120).returncode
except Exception as e:
    fail("--check did not run: %r" % e)
if code != 0:
    fail("--check exit code %s" % code)
print("\n".join(tail("iswm.log")))

proc = subprocess.Popen([exe, "--browser"])
ok = False
for _ in range(60):
    time.sleep(1)
    if any("serving" in line for line in tail("iswm.log", 200)):
        ok = True
        break
    if proc.poll() is not None:
        break
proc.kill()
if not ok:
    fail("app did not start (exit code %s)" % proc.poll())
print("app started fine")

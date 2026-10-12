"""Weighbridge reader.

Serial handling and regex parsing are adapted from adex_lite's
WeighbridgeManager: read lines from the indicator, pull the number out with
a configurable regex, apply a multiplier. Differences:
  * stability is time-based: readings over ``stable_seconds`` all within
    ``stable_tolerance_kg`` of each other;
  * the port is reopened automatically if the cable is pulled;
  * a simulator stands in for the indicator when ``simulate`` is on, so the
    app can be tried without hardware (it settles in about 3 seconds, as in
    the prototype).
"""
import collections
import random
import re
import threading
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # the simulator still works without pyserial
    serial = None

STALE_AFTER_S = 3.0
PARITY = {"None": "N", "Odd": "O", "Even": "E", "Mark": "M", "Space": "S"}


def list_ports():
    if serial is None:
        return []
    try:
        return [p.device for p in serial.tools.list_ports.comports()]
    except Exception:
        return []


class Weighbridge:
    def __init__(self, cfg):
        self._lock = threading.Lock()
        self._readings = collections.deque(maxlen=400)
        self._stop = threading.Event()
        self._thread = None
        self._sim = {"from": 0.0, "to": 0.0, "t0": 0.0}
        self.error = None
        self.seq = 0  # readings received since start; the screen blinks when it moves
        self.raw = ""  # last line from the indicator, for the tech team
        self.raw_at = 0.0
        self.configure(cfg)

    def configure(self, cfg):
        self.cfg = dict(cfg)
        try:
            self.pattern = re.compile(self.cfg.get("regex_pattern") or r"(\d+\.?\d*)")
        except re.error:
            self.pattern = re.compile(r"(\d+\.?\d*)")
        with self._lock:
            self._readings.clear()

    # lifecycle ---------------------------------------------------------
    def start(self):
        self.stop()
        self._stop.clear()
        target = self._sim_loop if self.cfg.get("simulate") else self._serial_loop
        self._thread = threading.Thread(target=target, daemon=True, name="weighbridge")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def restart(self, cfg):
        self.stop()
        self.configure(cfg)
        self.start()

    # readings ----------------------------------------------------------
    def parse(self, line):
        m = self.pattern.search(line)
        if not m:
            return None
        try:
            w = float(m.group(1)) * float(self.cfg.get("weight_multiplier") or 1)
        except (ValueError, IndexError):
            return None
        return w if 0 <= w <= 200000 else None

    def _push(self, w):
        with self._lock:
            self._readings.append((time.monotonic(), w))
            self.seq += 1

    def live(self):
        """Current weight and whether it has settled."""
        t = time.monotonic()
        with self._lock:
            readings = list(self._readings)
        if not readings or t - readings[-1][0] > STALE_AFTER_S:
            return {"connected": False, "weight": 0, "stable": False, "error": self.error, "seq": self.seq}
        window = float(self.cfg.get("stable_seconds") or 2.0)
        tol = float(self.cfg.get("stable_tolerance_kg") or 10)
        recent = [w for (rt, w) in readings if t - rt <= window]
        covered = t - window >= readings[0][0] - 0.25
        stable = covered and len(recent) >= 2 and (max(recent) - min(recent)) <= tol
        return {"connected": True, "weight": round(readings[-1][1]), "stable": stable, "error": None, "seq": self.seq}

    def debug(self):
        """For the Settings screen: what is coming in on the port."""
        t = time.monotonic()
        with self._lock:
            n = sum(1 for (rt, _) in self._readings if t - rt <= 5)
        return {"port": "Simulator" if self.cfg.get("simulate") else (self.cfg.get("com_port") or ""),
                "rate": round(n / 5.0, 1), "raw": self.raw if t - self.raw_at < 10 else "",
                "rawAge": round(t - self.raw_at, 1) if self.raw_at else None, "error": self.error,
                "running": bool(self._thread and self._thread.is_alive())}

    def capture(self):
        """The weight to save, or None if it is not settled above the minimum."""
        s = self.live()
        minimum = float(self.cfg.get("min_weight_kg") or 10)
        if s["connected"] and s["stable"] and s["weight"] > minimum:
            return float(s["weight"])
        return None

    # serial --------------------------------------------------------------
    def _open(self):
        c = self.cfg
        # serial_for_url also accepts socket://ip:port for indicators behind a network serial server
        return serial.serial_for_url(c["com_port"], baudrate=int(c.get("baud_rate") or 9600),
                                     bytesize=int(c.get("data_bits") or 8), parity=PARITY.get(c.get("parity"), "N"),
                                     stopbits=float(c.get("stop_bits") or 1), timeout=0.2, write_timeout=1.0)

    def _serial_loop(self):
        conn = None
        while not self._stop.is_set():
            if serial is None or not self.cfg.get("com_port"):
                self.error = "No COM port set" if serial else "pyserial missing"
                self._stop.wait(1.0)
                continue
            try:
                if conn is None or not conn.is_open:
                    conn = self._open()
                    self.error = None
                line = conn.readline().decode("ascii", errors="ignore").strip()
                if line:
                    self.raw, self.raw_at = line[:80], time.monotonic()
                    w = self.parse(line)
                    if w is not None:
                        self._push(w)
            except Exception as e:  # cable pulled, port busy, ...
                self.error = str(e)[:200]
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
                conn = None
                self._stop.wait(2.0)
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # simulator -----------------------------------------------------------
    def sim_load(self, target):
        """Simulator only: a vehicle drives on and the reading moves to ``target`` kg."""
        cur = self.live()["weight"]
        with self._lock:
            self._sim = {"from": float(cur), "to": float(max(0, target)), "t0": time.monotonic()}

    def _sim_loop(self):
        while not self._stop.is_set():
            s = self._sim
            p = min(1.0, (time.monotonic() - s["t0"]) / 3.0)
            ease = 1 - (1 - p) ** 3
            jitter = (random.random() - 0.5) * 220 * (1 - p)
            w = s["from"] + (s["to"] - s["from"]) * ease + jitter
            self._push(max(0.0, round(w / 10) * 10))
            self._stop.wait(0.11)

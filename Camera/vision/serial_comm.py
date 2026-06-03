"""
serial_comm.py — Arduino serial communication for Swachh MVP
Extends existing HMI protocol with ARM:PICK and ARM:NO_TARGET commands.
"""

import logging
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

try:
    import serial
    SERIAL_OK = True
except ImportError:
    SERIAL_OK = False
    log.warning("pyserial not installed — running in no-serial mode.")


class ArduinoSerial:
    """
    Serial interface to Arduino.

    Extends the existing Swachh HMI protocol:
      ARM:PICK:<cls>,<X>,<Y>,<Z>,<conf>\\n   → send pick target coordinates
      ARM:NO_TARGET\\n                        → no object detected

    Arduino must reply ACK:<msg>\\n or ERR:<msg>\\n within timeout.

    Parameters
    ----------
    cfg : dict
        Serial section from config.yaml.
    """

    def __init__(self, cfg: dict):
        self._port    = cfg.get("port",    "/dev/ttyACM0")
        self._baud    = cfg.get("baud",    115200)
        self._timeout = cfg.get("timeout", 0.5)
        self._ser     = None
        self._lock    = threading.Lock()
        self.connected = False

    def connect(self) -> bool:
        """Open serial connection. Returns True on success."""
        if not SERIAL_OK:
            log.warning("pyserial missing — serial disabled.")
            return False
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=self._timeout,
            )
            time.sleep(2)  # Wait for Arduino reset after serial open
            self._ser.reset_input_buffer()
            self.connected = True
            log.info(f"Arduino connected: {self._port} @ {self._baud}")
            return True
        except Exception as e:
            log.warning(f"Serial connect failed ({self._port}): {e}")
            self.connected = False
            return False

    def _send(self, command: str) -> Optional[str]:
        """
        Send a newline-terminated command, wait for ACK/ERR.
        Returns the response string or None on timeout/error.
        Thread-safe.
        """
        if not self.connected or self._ser is None:
            return None
        with self._lock:
            try:
                self._ser.reset_input_buffer()
                self._ser.write((command + "\n").encode("ascii"))
                self._ser.flush()

                # Wait for ACK or ERR within timeout
                deadline = time.time() + self._timeout
                while time.time() < deadline:
                    line = self._ser.readline().decode("ascii", errors="ignore").strip()
                    if line.startswith("ACK:") or line.startswith("ERR:"):
                        log.debug(f"TX → {command!r}  RX ← {line!r}")
                        return line
                log.warning(f"Timeout waiting for ACK on: {command!r}")
                return None
            except Exception as e:
                log.error(f"Serial send error: {e}")
                return None

    def send_pick(
        self,
        cls_name: str,
        X: Optional[float],
        Y: Optional[float],
        Z: Optional[float],
        conf: float,
    ) -> bool:
        """
        Send pick target coordinates to Arduino.

        Format: ARM:PICK:<cls>,<X>,<Y>,<Z>,<conf>

        Coordinate values are '?' when depth is unavailable.
        Returns True if ACK received.
        """
        x_str = f"{X:.1f}" if X is not None else "?"
        y_str = f"{Y:.1f}" if Y is not None else "?"
        z_str = f"{Z:.1f}" if Z is not None else "?"
        cmd   = f"ARM:PICK:{cls_name},{x_str},{y_str},{z_str},{conf:.2f}"
        resp  = self._send(cmd)
        ok    = resp is not None and resp.startswith("ACK:")
        if not ok:
            log.warning(f"send_pick failed — response: {resp!r}")
        return ok

    def send_no_target(self) -> bool:
        """Inform Arduino that no valid object is currently detected."""
        resp = self._send("ARM:NO_TARGET")
        return resp is not None and resp.startswith("ACK:")

    def disconnect(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self.connected = False
        log.info("Arduino serial disconnected.")

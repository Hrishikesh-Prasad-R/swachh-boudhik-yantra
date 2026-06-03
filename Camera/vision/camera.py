"""
camera.py — Stereo camera capture for Swachh MVP
Dual Logitech C270 @ 640x480, background threads, BW/color mode.
"""

import threading
import queue
import subprocess
import logging
import cv2
import numpy as np

log = logging.getLogger(__name__)


def _apply_v4l2_settings(device_path: str, cfg: dict) -> None:
    """Apply v4l2 camera settings matching calib.sh values."""
    controls = {
        "auto_exposure":             cfg.get("auto_exposure", 1),
        "exposure_time_absolute":    cfg.get("exposure", 151),
        "brightness":                cfg.get("brightness", 108),
        "gain":                      cfg.get("gain", 34),
        "white_balance_automatic":   cfg.get("auto_white_balance", 0),
        "power_line_frequency":      cfg.get("power_line_frequency", 1),
    }
    for ctrl, val in controls.items():
        cmd = ["v4l2-ctl", "-d", device_path, f"--set-ctrl={ctrl}={val}"]
        try:
            subprocess.run(cmd, capture_output=True, timeout=2)
        except Exception as e:
            log.warning(f"v4l2-ctl {ctrl} failed on {device_path}: {e}")


class _CamThread:
    """Single camera background thread — always holds the latest frame."""

    def __init__(self, device_id: int, width: int, height: int, fps: int):
        self.cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera /dev/video{device_id}")

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        # Force MJPEG for C270 — more stable than YUYV at 640x480@15fps
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        self._q = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            ok, frame = self.cap.read()
            if not ok:
                continue
            # Drop stale frame, always keep the newest
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self._q.put(frame)

    def read(self, timeout: float = 0.1):
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def release(self):
        self._stop.set()
        self._thread.join(timeout=1)
        self.cap.release()


class StereoCam:
    """
    Dual-camera stereo capture.

    Parameters
    ----------
    cfg : dict
        Camera section from config.yaml.
    use_color : bool
        If True, return BGR frames. If False, return grayscale frames.
    """

    def __init__(self, cfg: dict, use_color: bool = False):
        self.use_color = use_color
        w, h, fps = cfg["width"], cfg["height"], cfg["fps"]

        left_id  = cfg.get("left_device",  0)
        right_id = cfg.get("right_device", 2)

        log.info(f"Opening LEFT camera  → /dev/video{left_id}")
        log.info(f"Opening RIGHT camera → /dev/video{right_id}")

        # Apply v4l2 settings before opening capture
        _apply_v4l2_settings(f"/dev/video{left_id}",  cfg)
        _apply_v4l2_settings(f"/dev/video{right_id}", cfg)

        self._left  = _CamThread(left_id,  w, h, fps)
        self._right = _CamThread(right_id, w, h, fps)

        log.info("StereoCam ready.")

    def read(self):
        """
        Returns
        -------
        (left, right) : tuple[np.ndarray, np.ndarray] or (None, None)
            Frames in the configured color mode.
        """
        left  = self._left.read()
        right = self._right.read()

        if left is None or right is None:
            return None, None

        if not self.use_color:
            left  = cv2.cvtColor(left,  cv2.COLOR_BGR2GRAY)
            right = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)

        return left, right

    def read_gray(self):
        """Always returns grayscale regardless of use_color setting (for depth)."""
        left  = self._left.read()
        right = self._right.read()
        if left is None or right is None:
            return None, None
        return cv2.cvtColor(left,  cv2.COLOR_BGR2GRAY), \
               cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)

    def release(self):
        self._left.release()
        self._right.release()
        log.info("StereoCam released.")

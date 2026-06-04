#!/usr/bin/env python3
"""
rpi_publisher.py — Swachh Boudhik Yantra
Runs on the Raspberry Pi 5.

Responsibilities:
  1. Open stereo cameras (via existing camera.py)
  2. JPEG-compress both frames
  3. Publish over ZMQ to GPU worker (port 5555)
  4. Receive detection results from GPU (port 5556)
  5. Forward results to Arduino via serial_comm.py
  6. Display live feed with overlaid detections

Usage:
    cd Camera/vision
    python ../network/rpi_publisher.py
    python ../network/rpi_publisher.py --config ../network/network_config.yaml
    python ../network/rpi_publisher.py --test   # frame-only test, no Arduino
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import yaml

# ── Path setup: allow importing from Camera/vision/ ──────────────────────────
VISION_DIR = Path(__file__).resolve().parent.parent / "vision"
sys.path.insert(0, str(VISION_DIR))

from camera      import StereoCam
from serial_comm import ArduinoSerial

# ── ZMQ import ────────────────────────────────────────────────────────────────
try:
    import zmq
except ImportError:
    print("[ERROR] pyzmq not installed. Run: pip install pyzmq")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rpi_publisher")

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_config(net_cfg_path: str, vision_cfg_path: str) -> tuple[dict, dict]:
    with open(net_cfg_path) as f:
        net_cfg = yaml.safe_load(f)
    with open(vision_cfg_path) as f:
        vis_cfg = yaml.safe_load(f)
    return net_cfg, vis_cfg


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────
def _draw_detections(frame: np.ndarray, detections: list) -> None:
    """Draw bounding boxes + labels from GPU result dict list."""
    for i, det in enumerate(detections):
        x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
        label = f"{det['cls_name']} {det['conf']:.0%}"
        z = det.get("Z")
        if z is not None:
            label += f"  Z={z:.1f}cm"

        color = (0, 80, 255) if i == 0 else (0, 255, 80)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.circle(frame, ((x1+x2)//2, (y1+y2)//2), 5, color, -1)
        (tw, th), _ = cv2.getTextSize(label, FONT, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1+3, y1-4), FONT, 0.55,
                    (255, 255, 255), 1, cv2.LINE_AA)


def _draw_hud(frame: np.ndarray, fps: float, lat_ms: float,
              gpu_connected: bool, serial_ok: bool, last_cmd: str,
              tx_fps: float, rx_fps: float) -> None:
    h, _ = frame.shape[:2]
    lines = [
        f"TX: {tx_fps:.1f} fps  RX: {rx_fps:.1f} fps  Lat: {lat_ms:.0f}ms",
        f"GPU: {'CONNECTED' if gpu_connected else 'WAITING...'}  Serial: {'OK' if serial_ok else 'N/A'}",
    ]
    if last_cmd:
        lines.append(f"Sent: {last_cmd}")

    for i, line in enumerate(lines):
        y = 28 + i * 22
        cv2.putText(frame, line, (10, y), FONT, 0.55, (0,0,0), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (10, y), FONT, 0.55, (0,255,80), 1, cv2.LINE_AA)

    hint = "q=quit"
    cv2.putText(frame, hint, (10, h-10), FONT, 0.42, (180,180,180), 1, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────────────────────
# Stability tracker (mirrors main.py)
# ─────────────────────────────────────────────────────────────────────────────
class StabilityTracker:
    def __init__(self, required_frames: int):
        self.required = required_frames
        self._history: deque = deque(maxlen=required_frames)

    def update(self, cls_name: str | None) -> bool:
        self._history.append(cls_name)
        if len(self._history) < self.required:
            return False
        return all(c == cls_name for c in self._history) and cls_name is not None


# ─────────────────────────────────────────────────────────────────────────────
# Main publisher loop
# ─────────────────────────────────────────────────────────────────────────────
def main(args):
    # ── Load config ───────────────────────────────────────────────────────────
    net_cfg_path    = args.config
    vision_cfg_path = str(VISION_DIR / "config.yaml")

    if not os.path.isfile(net_cfg_path):
        log.error(f"Network config not found: {net_cfg_path}")
        sys.exit(1)
    if not os.path.isfile(vision_cfg_path):
        log.error(f"Vision config not found: {vision_cfg_path}")
        sys.exit(1)

    net_cfg, vis_cfg = load_config(net_cfg_path, vision_cfg_path)

    rpi_cfg    = net_cfg["rpi"]
    gpu_cfg    = net_cfg["gpu"]
    zmq_cfg    = net_cfg["zmq"]
    cam_cfg    = vis_cfg["camera"]
    serial_cfg = vis_cfg["serial"]

    rpi_host   = rpi_cfg["host"]
    pub_port   = rpi_cfg["pub_port"]
    pull_port  = rpi_cfg["pull_port"]
    jpeg_q     = gpu_cfg["jpeg_quality"]
    frame_skip = gpu_cfg["frame_skip"]
    recv_to    = gpu_cfg["recv_timeout_ms"]
    hwm        = zmq_cfg["hwm"]

    # ── ZMQ setup ─────────────────────────────────────────────────────────────
    log.info("Setting up ZMQ sockets...")
    ctx = zmq.Context()

    # PUB socket: RPi publishes frames → GPU subscribes
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.SNDHWM, hwm)
    pub.setsockopt(zmq.LINGER, zmq_cfg.get("linger_ms", 0))
    pub.bind(f"tcp://*:{pub_port}")
    log.info(f"ZMQ PUB bound → tcp://*:{pub_port}  (GPU will connect here)")

    # PULL socket: RPi receives detection results ← GPU pushes
    pull = ctx.socket(zmq.PULL)
    pull.setsockopt(zmq.RCVHWM, hwm)
    pull.setsockopt(zmq.LINGER, zmq_cfg.get("linger_ms", 0))
    pull.setsockopt(zmq.RCVTIMEO, recv_to)
    pull.bind(f"tcp://*:{pull_port}")
    log.info(f"ZMQ PULL bound → tcp://*:{pull_port}  (GPU will push results here)")

    # Give ZMQ time to bind
    time.sleep(0.5)

    # ── Camera ────────────────────────────────────────────────────────────────
    log.info("Initialising stereo cameras...")
    cam = StereoCam(cam_cfg, use_color=True)   # send color frames to GPU

    # ── Serial (optional in test mode) ────────────────────────────────────────
    arduino = None
    serial_ok = False
    if not args.test:
        arduino = ArduinoSerial(serial_cfg)
        serial_ok = arduino.connect()
        if not serial_ok:
            log.warning("Arduino not connected — running display-only.")

    # ── Stability tracker ─────────────────────────────────────────────────────
    tracker    = StabilityTracker(serial_cfg.get("stable_frames", 2))
    min_conf   = serial_cfg.get("min_conf_to_send", 0.55)

    # ── State ─────────────────────────────────────────────────────────────────
    frame_id       = 0
    fc             = 0
    last_dets      = []
    last_cmd       = ""
    gpu_connected  = False
    tx_times       = deque(maxlen=30)
    rx_times       = deque(maxlen=30)
    last_lat_ms    = 0.0
    sent_times: dict[int, float] = {}  # frame_id → send timestamp

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]

    log.info("Starting publisher loop. Waiting for GPU worker to connect...")
    cv2.namedWindow("Swachh — Distributed Mode (RPi)", cv2.WINDOW_NORMAL)

    try:
        while True:
            t_loop = time.perf_counter()

            # ── Capture ───────────────────────────────────────────────────────
            left, right = cam.read()
            if left is None:
                time.sleep(0.02)
                continue

            fc += 1

            # ── Publish frame (every frame_skip frames) ───────────────────────
            if fc % frame_skip == 0:
                _, left_jpg  = cv2.imencode(".jpg", left,  encode_params)
                _, right_jpg = cv2.imencode(".jpg", right, encode_params)

                msg = {
                    "frame_id":  frame_id,
                    "timestamp": time.time(),
                    "left_jpg":  left_jpg.tobytes(),
                    "right_jpg": right_jpg.tobytes(),
                }

                # ZMQ multipart: [topic_bytes, payload_bytes]
                payload = json.dumps({
                    "frame_id":  msg["frame_id"],
                    "timestamp": msg["timestamp"],
                }).encode()
                pub.send_multipart([
                    b"frame",
                    payload,
                    msg["left_jpg"],
                    msg["right_jpg"],
                ])

                sent_times[frame_id] = time.time()
                tx_times.append(time.perf_counter())
                frame_id += 1

            # ── Receive results (non-blocking) ────────────────────────────────
            try:
                raw = pull.recv_json(zmq.NOBLOCK)
                gpu_connected = True

                fid = raw.get("frame_id", -1)
                if fid in sent_times:
                    last_lat_ms = (time.time() - sent_times.pop(fid)) * 1000
                    # Clean up old entries
                    stale = [k for k in sent_times if k < fid - 30]
                    for k in stale:
                        sent_times.pop(k, None)

                rx_times.append(time.perf_counter())
                last_dets = raw.get("detections", [])

                # ── Serial command ────────────────────────────────────────────
                target_cls = last_dets[0]["cls_name"] if last_dets else None
                stable = tracker.update(target_cls)

                if (arduino and last_dets and stable
                        and last_dets[0]["conf"] >= min_conf):
                    best = last_dets[0]
                    sent = arduino.send_pick(
                        best["cls_name"],
                        best.get("X"), best.get("Y"), best.get("Z"),
                        best["conf"]
                    )
                    last_cmd = (
                        f"PICK {best['cls_name']} "
                        f"({best.get('X')},{best.get('Y')},{best.get('Z')}) "
                        f"{'✓' if sent else '✗'}"
                    )
                    log.info(last_cmd)

            except zmq.Again:
                pass  # No result yet — keep showing last detections

            # ── Display ───────────────────────────────────────────────────────
            display = left.copy() if left.ndim == 3 else \
                      cv2.cvtColor(left, cv2.COLOR_GRAY2BGR)
            _draw_detections(display, last_dets)

            # Compute FPS
            now = time.perf_counter()
            tx_fps = len([t for t in tx_times if now - t < 1.0])
            rx_fps = len([t for t in rx_times if now - t < 1.0])

            _draw_hud(display, fps=tx_fps, lat_ms=last_lat_ms,
                      gpu_connected=gpu_connected, serial_ok=serial_ok,
                      last_cmd=last_cmd, tx_fps=tx_fps, rx_fps=rx_fps)

            cv2.imshow("Swachh — Distributed Mode (RPi)", display)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                log.info("Quit requested.")
                break

    finally:
        log.info("Shutting down...")
        cam.release()
        if arduino:
            arduino.disconnect()
        pub.close()
        pull.close()
        ctx.term()
        cv2.destroyAllWindows()
        log.info("Shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Swachh RPi Publisher (ZMQ frame streamer)")
    p.add_argument(
        "--config", default=str(Path(__file__).parent / "network_config.yaml"),
        help="Path to network_config.yaml",
    )
    p.add_argument(
        "--test", action="store_true",
        help="Test mode: skip Arduino connection",
    )
    main(p.parse_args())

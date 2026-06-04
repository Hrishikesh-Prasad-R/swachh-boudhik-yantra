"""
gpu_worker.py — Swachh Boudhik Yantra
Runs on the Windows 11 GPU System (NVIDIA RTX A600).

Responsibilities:
  1. Connect to RPi ZMQ PUB socket, receive stereo frames
  2. Run YOLOv8s ONNX with CUDAExecutionProvider (RTX A600)
  3. Run stereo depth estimation (if stereo_calib.npz is present)
  4. Push detection results back to RPi via ZMQ PUSH

Usage (Windows CMD / PowerShell):
    cd Camera\\network
    python gpu_worker.py
    python gpu_worker.py --rpi-host 192.168.4.1
    python gpu_worker.py --no-depth       # skip depth if no calib file
    python gpu_worker.py --model path\\to\\yolov8s.onnx
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

# ── ZMQ import ────────────────────────────────────────────────────────────────
try:
    import zmq
except ImportError:
    print("[ERROR] pyzmq not installed.")
    print("  Run: pip install pyzmq")
    sys.exit(1)

# ── ONNX Runtime ──────────────────────────────────────────────────────────────
try:
    import onnxruntime as ort
    ONNX_OK = True
except ImportError:
    ONNX_OK = False
    print("[ERROR] onnxruntime not installed.")
    print("  Run: pip install onnxruntime-gpu")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gpu_worker")

# ── Add vision/ to path for detector + depth ──────────────────────────────────
# When running from Camera/network/ directory
SCRIPT_DIR  = Path(__file__).resolve().parent
VISION_DIR  = SCRIPT_DIR.parent / "vision"
sys.path.insert(0, str(VISION_DIR))

try:
    from detector import Detector, COCO_NAMES
    from depth    import StereoDepth
except ImportError as e:
    log.error(f"Cannot import vision modules from {VISION_DIR}: {e}")
    log.error("Make sure you have camera/vision/ directory alongside network/")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────
def load_configs(net_cfg_path: str, vision_cfg_path: str) -> tuple[dict, dict]:
    with open(net_cfg_path) as f:
        net_cfg = yaml.safe_load(f)
    with open(vision_cfg_path) as f:
        vis_cfg = yaml.safe_load(f)
    return net_cfg, vis_cfg


# ─────────────────────────────────────────────────────────────────────────────
# CUDA / Provider check
# ─────────────────────────────────────────────────────────────────────────────
def get_best_provider() -> list[str]:
    """Return ONNX execution providers in priority order: CUDA > CPU."""
    available = ort.get_available_providers()
    log.info(f"Available ONNX providers: {available}")

    if "CUDAExecutionProvider" in available:
        log.info("✓ CUDA is available — using GPU acceleration")
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    else:
        log.warning("✗ CUDA not available — falling back to CPU")
        log.warning("  Check: CUDA installed? onnxruntime-gpu installed?")
        return ["CPUExecutionProvider"]


# ─────────────────────────────────────────────────────────────────────────────
# Main worker loop
# ─────────────────────────────────────────────────────────────────────────────
def main(args):
    # ── Resolve config paths ──────────────────────────────────────────────────
    net_cfg_path    = args.config
    vision_cfg_path = str(VISION_DIR / "config.yaml")

    for p in [net_cfg_path, vision_cfg_path]:
        if not os.path.isfile(p):
            log.error(f"Config not found: {p}")
            sys.exit(1)

    net_cfg, vis_cfg = load_configs(net_cfg_path, vision_cfg_path)

    rpi_host   = args.rpi_host or net_cfg["rpi"]["host"]
    pub_port   = net_cfg["rpi"]["pub_port"]
    pull_port  = net_cfg["rpi"]["pull_port"]
    hwm        = net_cfg["zmq"]["hwm"]
    linger     = net_cfg["zmq"].get("linger_ms", 0)

    inf_cfg    = vis_cfg["inference"]
    depth_cfg  = vis_cfg["depth"]

    # ── Model path ────────────────────────────────────────────────────────────
    model_path = args.model or str(VISION_DIR / inf_cfg["onnx_path"])
    if not os.path.isfile(model_path):
        log.error(f"ONNX model not found: {model_path}")
        log.error("Copy yolov8s.onnx from the RPi: Camera/vision/models/yolov8s.onnx")
        sys.exit(1)

    # ── Provider check ────────────────────────────────────────────────────────
    providers = get_best_provider()

    # ── Load detector with CUDA ───────────────────────────────────────────────
    log.info(f"Loading YOLOv8 model: {model_path}")
    # Override provider in detector — patch the _ONNXEngine
    import onnxruntime as ort_inner
    _orig_init = ort_inner.InferenceSession.__init__

    def _patched_init(self_inner, path, **kwargs):
        kwargs["providers"] = providers
        _orig_init(self_inner, path, **kwargs)

    ort_inner.InferenceSession.__init__ = _patched_init

    detector = Detector(model_path, inf_cfg)
    log.info("Detector loaded with providers: %s", providers)

    # ── Load depth estimator ──────────────────────────────────────────────────
    calib_path = str(VISION_DIR / depth_cfg["calib_file"])
    depth_est  = None
    if not args.no_depth:
        log.info(f"Loading depth estimator (calib: {calib_path})...")
        depth_est = StereoDepth(calib_path, depth_cfg)
        if depth_est.ready:
            log.info("Stereo depth ready with calibration.")
        else:
            log.warning("Depth running in fallback mode (no calib file).")
    else:
        log.info("Depth estimation disabled (--no-depth).")

    # ── ZMQ setup ─────────────────────────────────────────────────────────────
    log.info(f"Connecting to RPi at {rpi_host}...")
    ctx = zmq.Context()

    # SUB socket: GPU subscribes to RPi frame stream
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.RCVHWM, hwm)
    sub.setsockopt(zmq.LINGER, linger)
    sub.setsockopt(zmq.RCVTIMEO, 5000)   # 5s timeout to detect disconnect
    sub.setsockopt_string(zmq.SUBSCRIBE, "frame")
    reconnect_ivl = net_cfg["zmq"].get("reconnect_ivl_ms", 500)
    sub.setsockopt(zmq.RECONNECT_IVL, reconnect_ivl)
    sub.connect(f"tcp://{rpi_host}:{pub_port}")
    log.info(f"ZMQ SUB → tcp://{rpi_host}:{pub_port}")

    # PUSH socket: GPU pushes results → RPi PULL
    push = ctx.socket(zmq.PUSH)
    push.setsockopt(zmq.SNDHWM, hwm)
    push.setsockopt(zmq.LINGER, linger)
    push.connect(f"tcp://{rpi_host}:{pull_port}")
    log.info(f"ZMQ PUSH → tcp://{rpi_host}:{pull_port}")

    # ── Stats ─────────────────────────────────────────────────────────────────
    rx_count   = 0
    tx_count   = 0
    err_count  = 0
    lat_dq     = deque(maxlen=60)
    fps_dq     = deque(maxlen=30)
    t_last_fps = time.perf_counter()

    log.info("GPU worker ready — waiting for frames from RPi...")
    log.info("Press Ctrl+C to stop.\n")

    try:
        while True:
            # ── Receive frame ─────────────────────────────────────────────────
            try:
                parts = sub.recv_multipart()
            except zmq.Again:
                log.warning("No frame received in 5s — is RPi publisher running?")
                continue

            t_recv = time.perf_counter()

            if len(parts) < 4:
                log.warning(f"Malformed message ({len(parts)} parts), skipping.")
                err_count += 1
                continue

            # parts: [topic, metadata_json, left_jpg_bytes, right_jpg_bytes]
            try:
                meta      = json.loads(parts[1].decode())
                frame_id  = meta["frame_id"]
                tx_time   = meta["timestamp"]

                left_jpg  = np.frombuffer(parts[2], dtype=np.uint8)
                right_jpg = np.frombuffer(parts[3], dtype=np.uint8)
                left      = cv2.imdecode(left_jpg,  cv2.IMREAD_COLOR)
                right     = cv2.imdecode(right_jpg, cv2.IMREAD_COLOR)

                if left is None or right is None:
                    log.warning(f"Frame {frame_id}: decode failed.")
                    err_count += 1
                    continue

            except Exception as e:
                log.error(f"Frame decode error: {e}")
                err_count += 1
                continue

            rx_count += 1

            # ── Detection ─────────────────────────────────────────────────────
            t_det_start = time.perf_counter()
            dets = detector.detect(left)
            t_det_end   = time.perf_counter()
            det_ms = (t_det_end - t_det_start) * 1000

            # ── Depth ─────────────────────────────────────────────────────────
            result_dets = []
            for i, det in enumerate(dets):
                d = {
                    "x1":      det.x1,
                    "y1":      det.y1,
                    "x2":      det.x2,
                    "y2":      det.y2,
                    "conf":    round(det.conf, 3),
                    "cls_id":  det.cls_id,
                    "cls_name": det.cls_name,
                    "X": None, "Y": None, "Z": None,
                }

                if depth_est and i == 0:  # depth only for best detection
                    if depth_est.ready:
                        left_g  = cv2.cvtColor(left,  cv2.COLOR_BGR2GRAY)
                        right_g = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
                        X, Y, Z = depth_est.compute(left_g, right_g,
                                                     det.cx, det.cy)
                        d["X"], d["Y"], d["Z"] = X, Y, Z
                    if d["Z"] is None:
                        d["Z"] = depth_est.fallback_depth(det.bbox_h)

                result_dets.append(d)

            # ── Push result back to RPi ───────────────────────────────────────
            result = {
                "frame_id":   frame_id,
                "detections": result_dets,
                "det_ms":     round(det_ms, 1),
            }
            try:
                push.send_json(result, zmq.NOBLOCK)
                tx_count += 1
            except zmq.Again:
                log.warning(f"Frame {frame_id}: result dropped (RPi PULL buffer full).")

            # ── Stats ─────────────────────────────────────────────────────────
            lat_ms = (time.time() - tx_time) * 1000
            lat_dq.append(lat_ms)
            fps_dq.append(time.perf_counter())

            now = time.perf_counter()
            fps = len([t for t in fps_dq if now - t < 1.0])

            if rx_count % 30 == 0:
                avg_lat = float(np.mean(lat_dq)) if lat_dq else 0
                log.info(
                    f"[Frame {frame_id:5d}]  "
                    f"FPS: {fps:4.1f}  "
                    f"Det: {det_ms:5.1f}ms  "
                    f"Lat: {avg_lat:5.1f}ms  "
                    f"Dets: {len(dets)}  "
                    f"Errors: {err_count}"
                )

    except KeyboardInterrupt:
        log.info("Interrupted by user.")

    finally:
        log.info(
            f"\n─── Session Summary ───\n"
            f"  Frames received:  {rx_count}\n"
            f"  Results sent:     {tx_count}\n"
            f"  Errors:           {err_count}\n"
            f"  Avg latency:      {float(np.mean(lat_dq)):.1f}ms\n"
            if lat_dq else
            f"\n─── Session Summary ───\n"
            f"  No frames received.\n"
        )
        sub.close()
        push.close()
        ctx.term()
        log.info("GPU worker shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Swachh GPU Worker — receives frames from RPi, returns detections"
    )
    p.add_argument(
        "--rpi-host", default=None,
        help="RPi IP address (default: from network_config.yaml → 192.168.4.1)",
    )
    p.add_argument(
        "--config",
        default=str(Path(__file__).parent / "network_config.yaml"),
        help="Path to network_config.yaml",
    )
    p.add_argument(
        "--model", default=None,
        help="Path to yolov8s.onnx (default: Camera/vision/models/yolov8s.onnx)",
    )
    p.add_argument(
        "--no-depth", action="store_true",
        help="Disable depth estimation (useful if stereo_calib.npz is not synced yet)",
    )
    main(p.parse_args())

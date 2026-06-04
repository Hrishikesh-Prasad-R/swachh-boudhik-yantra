"""
benchmark.py — Swachh Boudhik Yantra Network Benchmark
Run on either side to measure the transport layer performance.

Modes:
  --mode sender    : Simulate RPi — send test frames, measure TX rate
  --mode receiver  : Simulate GPU — receive frames, report RX rate + latency
  --mode roundtrip : Full round-trip test (requires gpu_worker.py running)

Usage:
    # On RPi:
    python benchmark.py --mode sender

    # On GPU system (Windows):
    python benchmark.py --mode receiver --rpi-host 192.168.4.1

    # Full round-trip (run gpu_worker.py first, then on RPi):
    python benchmark.py --mode roundtrip --duration 60
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

try:
    import zmq
except ImportError:
    print("[ERROR] pyzmq not installed. Run: pip install pyzmq")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("benchmark")

SCRIPT_DIR = Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────────────────────────
# Generate a synthetic test frame (no camera needed)
# ─────────────────────────────────────────────────────────────────────────────
def _make_test_frame(width=640, height=480, frame_id=0) -> np.ndarray:
    """Create a synthetic BGR frame with frame_id burned in."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 1] = 80   # dark green
    cv2.putText(frame, f"BENCH FRAME {frame_id}", (50, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# Sender mode (simulate RPi publisher)
# ─────────────────────────────────────────────────────────────────────────────
def run_sender(cfg: dict, args):
    net = cfg["rpi"]
    zmq_cfg = cfg["zmq"]
    jpeg_q  = cfg["gpu"]["jpeg_quality"]

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.SNDHWM, zmq_cfg["hwm"])
    pub.setsockopt(zmq.LINGER, 0)
    pub.bind(f"tcp://*:{net['pub_port']}")
    log.info(f"Sender PUB → tcp://*:{net['pub_port']}")
    time.sleep(1.0)   # ZMQ subscription delay

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]
    frame_id = 0
    t_start  = time.perf_counter()
    t_report = t_start
    fps_dq   = deque(maxlen=60)
    bytes_sent = 0

    log.info(f"Sending for {args.duration}s at ~{args.fps} FPS target...")
    frame_interval = 1.0 / args.fps

    try:
        while time.perf_counter() - t_start < args.duration:
            t0 = time.perf_counter()

            left  = _make_test_frame(frame_id=frame_id)
            right = _make_test_frame(frame_id=frame_id)

            _, left_jpg  = cv2.imencode(".jpg", left,  encode_params)
            _, right_jpg = cv2.imencode(".jpg", right, encode_params)

            meta = json.dumps({
                "frame_id":  frame_id,
                "timestamp": time.time(),
            }).encode()

            pub.send_multipart([
                b"frame",
                meta,
                left_jpg.tobytes(),
                right_jpg.tobytes(),
            ])

            bytes_sent += len(left_jpg) + len(right_jpg) + len(meta)
            fps_dq.append(t0)
            frame_id += 1

            # Rate limiting
            elapsed = time.perf_counter() - t0
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)

            # Report every 5s
            now = time.perf_counter()
            if now - t_report >= 5.0:
                fps = len([t for t in fps_dq if now - t < 1.0])
                mbps = (bytes_sent * 8 / 1e6) / (now - t_start)
                log.info(f"TX: {fps:.1f} FPS  |  {mbps:.2f} Mbps  |  frames: {frame_id}")
                t_report = now

    except KeyboardInterrupt:
        pass

    total_s = time.perf_counter() - t_start
    avg_fps = frame_id / total_s
    avg_mbps = (bytes_sent * 8 / 1e6) / total_s

    _print_report("SENDER", {
        "Duration (s)":    f"{total_s:.1f}",
        "Frames sent":     frame_id,
        "Avg TX FPS":      f"{avg_fps:.2f}",
        "Avg Bandwidth":   f"{avg_mbps:.2f} Mbps",
        "JPEG Quality":    jpeg_q,
        "Frame Size":      f"~{bytes_sent // max(frame_id,1) // 1024} KB/frame",
    })

    pub.close()
    ctx.term()


# ─────────────────────────────────────────────────────────────────────────────
# Receiver mode (simulate GPU receiver, no detection)
# ─────────────────────────────────────────────────────────────────────────────
def run_receiver(cfg: dict, args):
    rpi_host = args.rpi_host or cfg["rpi"]["host"]
    net      = cfg["rpi"]
    zmq_cfg  = cfg["zmq"]

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.RCVHWM, zmq_cfg["hwm"])
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.RCVTIMEO, 5000)
    sub.setsockopt_string(zmq.SUBSCRIBE, "frame")
    sub.connect(f"tcp://{rpi_host}:{net['pub_port']}")
    log.info(f"Receiver SUB → tcp://{rpi_host}:{net['pub_port']}")
    log.info("Waiting for frames... (start sender on RPi)")

    rx_count = 0
    lat_dq   = deque(maxlen=200)
    fps_dq   = deque(maxlen=60)
    dropped  = 0
    t_start  = None
    t_report = time.perf_counter()

    try:
        while True:
            try:
                parts = sub.recv_multipart()
            except zmq.Again:
                if t_start and time.perf_counter() - t_start > args.duration:
                    break
                log.warning("No frame in 5s — waiting...")
                continue

            t_recv = time.perf_counter()
            if t_start is None:
                t_start = t_recv
                log.info("First frame received — benchmark started.")

            if time.perf_counter() - t_start > args.duration:
                break

            if len(parts) < 4:
                dropped += 1
                continue

            meta = json.loads(parts[1].decode())
            lat_ms = (time.time() - meta["timestamp"]) * 1000
            lat_dq.append(lat_ms)
            fps_dq.append(t_recv)
            rx_count += 1

            now = time.perf_counter()
            if now - t_report >= 5.0:
                fps = len([t for t in fps_dq if now - t < 1.0])
                avg_lat = float(np.mean(lat_dq))
                log.info(f"RX: {fps:.1f} FPS  |  Lat: {avg_lat:.1f}ms avg  |  frames: {rx_count}")
                t_report = now

    except KeyboardInterrupt:
        pass

    total_s = (time.perf_counter() - t_start) if t_start else 1.0
    _print_report("RECEIVER", {
        "Duration (s)":    f"{total_s:.1f}",
        "Frames received": rx_count,
        "Avg RX FPS":      f"{rx_count/total_s:.2f}",
        "Avg Latency":     f"{float(np.mean(lat_dq)):.1f} ms" if lat_dq else "N/A",
        "Min Latency":     f"{float(np.min(lat_dq)):.1f} ms"  if lat_dq else "N/A",
        "Max Latency":     f"{float(np.max(lat_dq)):.1f} ms"  if lat_dq else "N/A",
        "Dropped":         dropped,
    })
    sub.close()
    ctx.term()


# ─────────────────────────────────────────────────────────────────────────────
# Round-trip mode (RPi sends frames, waits for GPU results)
# ─────────────────────────────────────────────────────────────────────────────
def run_roundtrip(cfg: dict, args):
    net     = cfg["rpi"]
    zmq_cfg = cfg["zmq"]
    jpeg_q  = cfg["gpu"]["jpeg_quality"]

    ctx = zmq.Context()

    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.SNDHWM, zmq_cfg["hwm"])
    pub.setsockopt(zmq.LINGER, 0)
    pub.bind(f"tcp://*:{net['pub_port']}")

    pull = ctx.socket(zmq.PULL)
    pull.setsockopt(zmq.RCVHWM, zmq_cfg["hwm"])
    pull.setsockopt(zmq.LINGER, 0)
    pull.setsockopt(zmq.RCVTIMEO, cfg["gpu"]["recv_timeout_ms"])
    pull.bind(f"tcp://*:{net['pull_port']}")

    log.info(f"Round-trip PUB → *:{net['pub_port']}  PULL ← *:{net['pull_port']}")
    log.info("Make sure gpu_worker.py is running on the GPU system.")
    time.sleep(1.0)

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]
    frame_id = 0
    rt_dq    = deque(maxlen=200)
    sent_ts: dict[int, float] = {}
    rx_count = 0
    timeout_count = 0
    t_start = time.perf_counter()
    t_report = t_start
    fps_dq = deque(maxlen=60)
    frame_interval = 1.0 / args.fps

    try:
        while time.perf_counter() - t_start < args.duration:
            t0 = time.perf_counter()

            frame = _make_test_frame(frame_id=frame_id)
            _, jpg = cv2.imencode(".jpg", frame, encode_params)
            meta = json.dumps({"frame_id": frame_id, "timestamp": time.time()}).encode()

            pub.send_multipart([b"frame", meta, jpg.tobytes(), jpg.tobytes()])
            sent_ts[frame_id] = time.time()
            fps_dq.append(t0)
            frame_id += 1

            # Try receive result
            try:
                res = pull.recv_json(zmq.NOBLOCK)
                fid = res.get("frame_id", -1)
                if fid in sent_ts:
                    rt_ms = (time.time() - sent_ts.pop(fid)) * 1000
                    rt_dq.append(rt_ms)
                    rx_count += 1
            except zmq.Again:
                timeout_count += 1

            elapsed = time.perf_counter() - t0
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)

            now = time.perf_counter()
            if now - t_report >= 5.0:
                fps = len([t for t in fps_dq if now - t < 1.0])
                avg_rt = float(np.mean(rt_dq)) if rt_dq else 0
                log.info(f"FPS: {fps:.1f}  |  RT: {avg_rt:.1f}ms  |  rx: {rx_count}/{frame_id}")
                t_report = now

    except KeyboardInterrupt:
        pass

    total_s = time.perf_counter() - t_start
    _print_report("ROUND-TRIP", {
        "Duration (s)":      f"{total_s:.1f}",
        "Frames sent":       frame_id,
        "Results received":  rx_count,
        "Timeouts":          timeout_count,
        "TX FPS":            f"{frame_id/total_s:.2f}",
        "Effective FPS":     f"{rx_count/total_s:.2f}",
        "Avg Round-Trip":    f"{float(np.mean(rt_dq)):.1f} ms" if rt_dq else "N/A",
        "Min Round-Trip":    f"{float(np.min(rt_dq)):.1f} ms"  if rt_dq else "N/A",
        "Max Round-Trip":    f"{float(np.max(rt_dq)):.1f} ms"  if rt_dq else "N/A",
    }, save=True)

    pub.close()
    pull.close()
    ctx.term()


# ─────────────────────────────────────────────────────────────────────────────
def _print_report(title: str, data: dict, save: bool = False):
    lines = [
        "",
        "╔══════════════════════════════════════════════╗",
        f"║   Benchmark Report: {title:<24}║",
        "╠══════════════════════════════════════════════╣",
    ]
    for k, v in data.items():
        lines.append(f"║  {k:<22} {str(v):<21}║")
    lines += [
        "╚══════════════════════════════════════════════╝",
        "",
    ]
    report = "\n".join(lines)
    print(report)

    if save:
        out = SCRIPT_DIR / "benchmark_report.txt"
        with open(out, "w") as f:
            f.write(report)
        log.info(f"Report saved to {out}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Swachh Network Benchmark")
    p.add_argument("--mode", choices=["sender", "receiver", "roundtrip"],
                   default="roundtrip", help="Benchmark mode")
    p.add_argument("--rpi-host", default=None,
                   help="RPi IP (receiver mode only, default from config)")
    p.add_argument("--config",
                   default=str(SCRIPT_DIR / "network_config.yaml"),
                   help="Path to network_config.yaml")
    p.add_argument("--duration", type=float, default=30.0,
                   help="Benchmark duration in seconds (default: 30)")
    p.add_argument("--fps", type=float, default=10.0,
                   help="Target FPS (default: 10)")
    args = p.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    if args.mode == "sender":
        run_sender(cfg, args)
    elif args.mode == "receiver":
        run_receiver(cfg, args)
    else:
        run_roundtrip(cfg, args)

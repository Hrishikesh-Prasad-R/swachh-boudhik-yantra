"""
journal_benchmark.py — Swachh Boudhik Yantra
Comprehensive benchmarking suite for Q1 journal publication.

Runs on the WINDOWS GPU system while gpu_worker.py is active.
Injects synthetic frames, captures per-frame measurements, and
writes a publication-ready CSV + summary report.

Metrics captured (per frame):
  Network:
    - frame_tx_timestamp          : wall-clock time frame was sent
    - frame_rx_timestamp          : wall-clock time result was received
    - network_one_way_ms          : estimated one-way transport latency (ZMQ)
    - round_trip_ms               : full send→detect→receive latency
    - frame_size_left_bytes       : compressed JPEG size (left cam)
    - frame_size_right_bytes      : compressed JPEG size (right cam)
    - total_payload_bytes         : total bytes per message
    - throughput_mbps             : instantaneous bandwidth at send time

  Inference (reported by gpu_worker in result JSON):
    - det_ms                      : YOLOv8 inference time on GPU (ms)
    - num_detections              : count of objects detected

  Per-detection (flattened, detection 0 only for primary target):
    - det0_class                  : COCO class name
    - det0_confidence             : detection confidence score
    - det0_x1, y1, x2, y2        : bounding box pixels
    - det0_cx, det0_cy            : centroid pixels
    - det0_X_m, Y_m, Z_m         : 3D world coordinates (metres, if depth active)

  System / GPU (sampled at send time):
    - gpu_util_pct                : GPU utilisation (nvidia-smi)
    - gpu_mem_used_mb             : GPU memory used (MiB)
    - gpu_temp_c                  : GPU temperature (°C)
    - cpu_util_pct                : CPU utilisation (psutil)
    - ram_used_mb                 : RAM used (MiB)

  Quality:
    - result_timeout              : 1 if no result received for this frame
    - frame_dropped_zmq           : 1 if ZMQ dropped (HWM hit)
    - jpeg_quality                : JPEG quality setting used

Usage (Windows GPU system, gpu_worker.py must be running):
    python journal_benchmark.py --duration 120 --fps 10
    python journal_benchmark.py --duration 60  --fps 5 --out my_bench.csv
"""

import argparse
import csv
import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

try:
    import zmq
except ImportError:
    print("[ERROR] pyzmq not installed. Run: pip install pyzmq")
    sys.exit(1)

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False
    print("[WARN] psutil not installed — CPU/RAM metrics will be N/A. Run: pip install psutil")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("journal_benchmark")

SCRIPT_DIR = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────────
# CSV column order (publication-friendly names)
# ─────────────────────────────────────────────────────────────────────────────
CSV_COLUMNS = [
    # Identity
    "frame_id",
    "wall_clock_utc",
    # Network transport
    "network_one_way_ms",
    "round_trip_ms",
    "frame_size_left_bytes",
    "frame_size_right_bytes",
    "total_payload_bytes",
    "throughput_mbps",
    # Inference
    "det_ms",
    "num_detections",
    # Primary detection
    "det0_class",
    "det0_confidence",
    "det0_x1", "det0_y1", "det0_x2", "det0_y2",
    "det0_cx", "det0_cy",
    "det0_X_m", "det0_Y_m", "det0_Z_m",
    # System resources
    "gpu_util_pct",
    "gpu_mem_used_mb",
    "gpu_temp_c",
    "cpu_util_pct",
    "ram_used_mb",
    # Quality flags
    "result_timeout",
    "jpeg_quality",
]


# ─────────────────────────────────────────────────────────────────────────────
# GPU stats via nvidia-smi (non-blocking, polled in a background thread)
# ─────────────────────────────────────────────────────────────────────────────
class GPUMonitor:
    """Background thread that polls nvidia-smi every second."""

    def __init__(self):
        self._lock = threading.Lock()
        self._util = None
        self._mem  = None
        self._temp = None
        self._running = False
        self._thread = threading.Thread(target=self._poll, daemon=True)

    def start(self):
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False

    def _poll(self):
        while self._running:
            try:
                result = subprocess.run(
                    ["nvidia-smi",
                     "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    parts = [p.strip() for p in result.stdout.strip().split(",")]
                    if len(parts) >= 3:
                        with self._lock:
                            self._util = float(parts[0])
                            self._mem  = float(parts[1])
                            self._temp = float(parts[2])
            except Exception:
                pass
            time.sleep(1.0)

    def snapshot(self):
        with self._lock:
            return self._util, self._mem, self._temp


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic frame generator (no real camera needed on this side)
# ─────────────────────────────────────────────────────────────────────────────
def _make_test_frame(width=640, height=480, frame_id=0, pattern="gradient") -> np.ndarray:
    """
    Generate a realistic synthetic BGR frame.
    pattern='gradient'  — colour gradient with frame ID (stresses JPEG codec)
    pattern='noise'     — random noise (worst-case JPEG size)
    pattern='solid'     — flat colour (best-case JPEG size)
    """
    if pattern == "noise":
        frame = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    elif pattern == "solid":
        frame = np.full((height, width, 3), 80, dtype=np.uint8)
    else:  # gradient
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = np.linspace(0, 200, width, dtype=np.uint8)      # B
        frame[:, :, 1] = np.linspace(0, 180, height, dtype=np.uint8).reshape(-1, 1)  # G
        frame[:, :, 2] = (frame_id % 256)  # R cycles with frame_id
    cv2.putText(frame, f"BENCH #{frame_id}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# Main benchmark loop
# ─────────────────────────────────────────────────────────────────────────────
def run_benchmark(cfg: dict, args):
    net     = cfg["rpi"]
    zmq_cfg = cfg["zmq"]
    jpeg_q  = cfg["gpu"]["jpeg_quality"]
    recv_to = cfg["gpu"]["recv_timeout_ms"]

    # ── ZMQ sockets ──────────────────────────────────────────────────────────
    # The benchmark acts AS the RPi (publisher side).
    # It must BIND so the gpu_worker (pointing at 127.0.0.1) can connect to it.
    # Before running: restart gpu_worker with --rpi-host 127.0.0.1
    ctx = zmq.Context()

    # PUB: bind locally — gpu_worker SUBs to us
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.SNDHWM, zmq_cfg["hwm"])
    pub.setsockopt(zmq.LINGER, 0)
    pub.bind(f"tcp://*:{net['pub_port']}")
    log.info(f"PUB BIND tcp://*:{net['pub_port']}  (gpu_worker must use --rpi-host 127.0.0.1)")

    # PULL: bind locally — gpu_worker PUSHes results to us
    pull = ctx.socket(zmq.PULL)
    pull.setsockopt(zmq.RCVHWM, zmq_cfg["hwm"])
    pull.setsockopt(zmq.LINGER, 0)
    pull.setsockopt(zmq.RCVTIMEO, recv_to)
    pull.bind(f"tcp://*:{net['pull_port']}")
    log.info(f"PULL BIND tcp://*:{net['pull_port']}")

    # ── System monitors ───────────────────────────────────────────────────────
    gpu_mon = GPUMonitor()
    gpu_mon.start()
    log.info("GPU monitor started.")

    time.sleep(1.5)  # let ZMQ subscription settle

    # ── Output CSV setup ──────────────────────────────────────────────────────
    out_path = Path(args.out)
    csv_file = open(out_path, "w", newline="", encoding="utf-8")
    writer   = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    log.info(f"Writing per-frame data → {out_path.resolve()}")

    # ── Encode params ─────────────────────────────────────────────────────────
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_q]
    frame_interval = 1.0 / args.fps

    # ── Accumulators for summary stats ────────────────────────────────────────
    sent_ts: dict[int, float] = {}
    records = []

    rt_all    = []
    det_all   = []
    lat_all   = []
    bw_all    = []
    drop_count = 0
    timeout_count = 0

    frame_id = 0
    t_start  = time.perf_counter()
    t_report = t_start

    log.info(f"Benchmark running for {args.duration}s @ {args.fps} FPS target...")
    log.info("Make sure gpu_worker.py is running and RPi publisher is STOPPED (benchmark injects its own frames).")
    print()

    try:
        while time.perf_counter() - t_start < args.duration:
            t_loop = time.perf_counter()

            # ── Build and encode frame ────────────────────────────────────────
            left_frame  = _make_test_frame(frame_id=frame_id, pattern=args.pattern)
            right_frame = _make_test_frame(frame_id=frame_id, pattern=args.pattern)

            _, left_jpg  = cv2.imencode(".jpg", left_frame,  encode_params)
            _, right_jpg = cv2.imencode(".jpg", right_frame, encode_params)

            left_bytes  = left_jpg.tobytes()
            right_bytes = right_jpg.tobytes()
            left_sz  = len(left_bytes)
            right_sz = len(right_bytes)
            total_sz = left_sz + right_sz

            tx_wall = time.time()
            meta = json.dumps({
                "frame_id":  frame_id,
                "timestamp": tx_wall,
            }).encode()

            # ── Send ──────────────────────────────────────────────────────────
            try:
                pub.send_multipart(
                    [b"frame", meta, left_bytes, right_bytes],
                    zmq.NOBLOCK
                )
                sent_ts[frame_id] = tx_wall
            except zmq.Again:
                drop_count += 1
                frame_id += 1
                continue

            # Instantaneous bandwidth (bytes this frame × 8 / interval)
            bw_mbps = (total_sz * 8 / 1e6) / frame_interval

            # ── Snapshot system state ─────────────────────────────────────────
            gpu_util, gpu_mem, gpu_temp = gpu_mon.snapshot()
            cpu_pct  = psutil.cpu_percent(interval=None) if PSUTIL_OK else None
            ram_mb   = (psutil.virtual_memory().used / 1e6) if PSUTIL_OK else None

            # ── Collect result from gpu_worker ────────────────────────────────
            row = {c: "" for c in CSV_COLUMNS}
            row["frame_id"]               = frame_id
            row["wall_clock_utc"]         = datetime.utcfromtimestamp(tx_wall).isoformat()
            row["frame_size_left_bytes"]  = left_sz
            row["frame_size_right_bytes"] = right_sz
            row["total_payload_bytes"]    = total_sz
            row["throughput_mbps"]        = round(bw_mbps, 4)
            row["jpeg_quality"]           = jpeg_q
            row["gpu_util_pct"]           = gpu_util if gpu_util is not None else ""
            row["gpu_mem_used_mb"]        = gpu_mem  if gpu_mem  is not None else ""
            row["gpu_temp_c"]             = gpu_temp if gpu_temp is not None else ""
            row["cpu_util_pct"]           = round(cpu_pct, 1) if cpu_pct is not None else ""
            row["ram_used_mb"]            = round(ram_mb, 0)  if ram_mb  is not None else ""
            row["result_timeout"]         = 0

            try:
                res = pull.recv_json()   # blocks up to recv_timeout_ms
                rx_wall = time.time()
                fid     = res.get("frame_id", -1)

                if fid in sent_ts:
                    rt_ms  = (rx_wall - sent_ts.pop(fid)) * 1000
                    net_ms = (rx_wall - tx_wall) * 1000   # one-way approximation
                else:
                    rt_ms  = (rx_wall - tx_wall) * 1000
                    net_ms = rt_ms

                det_ms   = res.get("det_ms", 0)
                dets     = res.get("detections", [])
                num_dets = len(dets)

                row["network_one_way_ms"] = round(net_ms, 3)
                row["round_trip_ms"]      = round(rt_ms,  3)
                row["det_ms"]             = round(det_ms, 3)
                row["num_detections"]     = num_dets

                if dets:
                    d = dets[0]
                    row["det0_class"]      = d.get("cls_name", "")
                    row["det0_confidence"] = round(d.get("conf",  0.0), 4)
                    row["det0_x1"]         = d.get("x1", "")
                    row["det0_y1"]         = d.get("y1", "")
                    row["det0_x2"]         = d.get("x2", "")
                    row["det0_y2"]         = d.get("y2", "")
                    row["det0_cx"]         = d.get("cx", "") if "cx" in d else ""
                    row["det0_cy"]         = d.get("cy", "") if "cy" in d else ""
                    row["det0_X_m"]        = d.get("X", "") if d.get("X") is not None else ""
                    row["det0_Y_m"]        = d.get("Y", "") if d.get("Y") is not None else ""
                    row["det0_Z_m"]        = d.get("Z", "") if d.get("Z") is not None else ""

                rt_all.append(rt_ms)
                det_all.append(det_ms)
                lat_all.append(net_ms)
                bw_all.append(bw_mbps)

            except zmq.Again:
                row["result_timeout"]     = 1
                row["round_trip_ms"]      = ""
                row["network_one_way_ms"] = ""
                row["det_ms"]             = ""
                timeout_count += 1
                # clean up stale sent_ts entry
                sent_ts.pop(frame_id, None)

            writer.writerow(row)
            records.append(row)
            frame_id += 1

            # ── Progress report every 10s ─────────────────────────────────────
            now = time.perf_counter()
            elapsed = now - t_start
            if now - t_report >= 10.0:
                rx_ok = len(rt_all)
                avg_rt  = np.mean(rt_all[-60:])  if rt_all  else 0
                avg_det = np.mean(det_all[-60:]) if det_all else 0
                fps_act = rx_ok / elapsed if elapsed > 0 else 0
                log.info(
                    f"[{elapsed:5.0f}s/{args.duration:.0f}s] "
                    f"Sent:{frame_id}  Rx:{rx_ok}  Timeout:{timeout_count}  "
                    f"FPS:{fps_act:.1f}  RT:{avg_rt:.1f}ms  Det:{avg_det:.1f}ms"
                )
                t_report = now

            # ── Rate limit ────────────────────────────────────────────────────
            loop_elapsed = time.perf_counter() - t_loop
            if loop_elapsed < frame_interval:
                time.sleep(frame_interval - loop_elapsed)

    except KeyboardInterrupt:
        log.info("Benchmark interrupted by user.")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    gpu_mon.stop()
    csv_file.flush()
    csv_file.close()
    pub.close()
    pull.close()
    ctx.term()

    total_s = time.perf_counter() - t_start

    # ── Compute summary statistics ────────────────────────────────────────────
    def _stats(arr):
        if not arr:
            return {"mean": "N/A", "std": "N/A", "min": "N/A",
                    "max": "N/A", "p50": "N/A", "p95": "N/A", "p99": "N/A"}
        a = np.array(arr)
        return {
            "mean": f"{np.mean(a):.3f}",
            "std":  f"{np.std(a):.3f}",
            "min":  f"{np.min(a):.3f}",
            "max":  f"{np.max(a):.3f}",
            "p50":  f"{np.percentile(a, 50):.3f}",
            "p95":  f"{np.percentile(a, 95):.3f}",
            "p99":  f"{np.percentile(a, 99):.3f}",
        }

    rt_s   = _stats(rt_all)
    det_s  = _stats(det_all)
    lat_s  = _stats(lat_all)
    bw_s   = _stats(bw_all)

    rx_ok  = len(rt_all)
    pdr    = (rx_ok / max(frame_id, 1)) * 100   # packet delivery ratio
    tpr    = (timeout_count / max(frame_id, 1)) * 100

    # ── Print publication summary ─────────────────────────────────────────────
    sep = "═" * 58
    print()
    print(f"╔{sep}╗")
    print(f"║   JOURNAL BENCHMARK REPORT — Swachh Boudhik Yantra{'':6}║")
    print(f"║   {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'):<54}║")
    print(f"╠{sep}╣")
    print(f"║  Platform: {platform.node():<46}║")
    print(f"║  Duration:           {total_s:.1f} s{'':30}║")
    print(f"║  Frames sent:        {frame_id:<36}║")
    print(f"║  Results received:   {rx_ok:<36}║")
    print(f"║  Timeouts:           {timeout_count} ({tpr:.1f}%){'':26}║")
    print(f"║  ZMQ drops:          {drop_count:<36}║")
    print(f"║  Packet Delivery:    {pdr:.2f}%{'':31}║")
    print(f"║  Effective FPS:      {rx_ok/total_s:.2f}{'':32}║")
    print(f"╠{sep}╣")
    print(f"║  ROUND-TRIP LATENCY (ms){'':33}║")
    print(f"║    Mean ± Std:       {rt_s['mean']} ± {rt_s['std']} ms{'':19}║")
    print(f"║    Min / Max:        {rt_s['min']} / {rt_s['max']} ms{'':19}║")
    print(f"║    P50 / P95 / P99:  {rt_s['p50']} / {rt_s['p95']} / {rt_s['p99']} ms{'':7}║")
    print(f"╠{sep}╣")
    print(f"║  GPU INFERENCE TIME (ms){'':33}║")
    print(f"║    Mean ± Std:       {det_s['mean']} ± {det_s['std']} ms{'':19}║")
    print(f"║    Min / Max:        {det_s['min']} / {det_s['max']} ms{'':19}║")
    print(f"║    P50 / P95 / P99:  {det_s['p50']} / {det_s['p95']} / {det_s['p99']} ms{'':7}║")
    print(f"╠{sep}╣")
    print(f"║  NETWORK BANDWIDTH (Mbps){'':32}║")
    print(f"║    Mean:             {bw_s['mean']} Mbps{'':28}║")
    print(f"║    Min / Max:        {bw_s['min']} / {bw_s['max']} Mbps{'':21}║")
    print(f"╠{sep}╣")
    print(f"║  OUTPUT{'':50}║")
    print(f"║    CSV: {str(out_path.resolve()):<49}║")
    print(f"╚{sep}╝")
    print()

    # ── Save machine-readable summary JSON ────────────────────────────────────
    summary = {
        "timestamp_utc":     datetime.utcnow().isoformat(),
        "platform":          platform.node(),
        "duration_s":        round(total_s, 2),
        "target_fps":        args.fps,
        "jpeg_quality":      jpeg_q,
        "frames_sent":       frame_id,
        "frames_received":   rx_ok,
        "timeouts":          timeout_count,
        "zmq_drops":         drop_count,
        "packet_delivery_ratio_pct": round(pdr, 4),
        "effective_fps":     round(rx_ok / total_s, 4),
        "round_trip_ms":     rt_s,
        "inference_ms":      det_s,
        "one_way_latency_ms": lat_s,
        "bandwidth_mbps":    bw_s,
        "csv_path":          str(out_path.resolve()),
    }
    summary_path = out_path.with_suffix(".summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Summary JSON → {summary_path}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Swachh Boudhik Yantra — Journal-Grade Benchmark"
    )
    p.add_argument(
        "--duration", type=float, default=120.0,
        help="Benchmark duration in seconds (default: 120 for journal quality)"
    )
    p.add_argument(
        "--fps", type=float, default=10.0,
        help="Target frame rate (default: 10)"
    )
    p.add_argument(
        "--rpi-host", default=None,
        help="RPi IP override (default: from network_config.yaml)"
    )
    p.add_argument(
        "--config",
        default=str(SCRIPT_DIR / "network_config.yaml"),
        help="Path to network_config.yaml"
    )
    p.add_argument(
        "--out",
        default=str(SCRIPT_DIR / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
        help="Output CSV path"
    )
    p.add_argument(
        "--pattern", choices=["gradient", "noise", "solid"], default="gradient",
        help="Synthetic frame pattern (gradient=realistic, noise=worst-case JPEG)"
    )
    args = p.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    run_benchmark(cfg, args)

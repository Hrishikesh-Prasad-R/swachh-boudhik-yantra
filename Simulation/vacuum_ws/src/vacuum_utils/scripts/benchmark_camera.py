#!/usr/bin/env python3
"""
benchmark_camera.py  —  Stage 3 (D435i Perception Pipeline)
─────────────────────────────────────────────────────────────
Runs a timed benchmark on the simulated D435i perception pipeline.
Records per-frame statistics and outputs a CSV report.

Usage:
  # From workspace root (source install/setup.bash first):
  python3.12 src/vacuum_utils/scripts/benchmark_camera.py

  # Custom duration and output:
  python3.12 src/vacuum_utils/scripts/benchmark_camera.py \
      --duration 120 \
      --output bags/stage3/benchmark_results.csv \
      --noise-mode ideal

Output CSV columns:
  timestamp_s, color_fps, depth_fps, points_fps,
  color_latency_ms, depth_latency_ms, points_latency_ms,
  cpu_pct, ram_mb

Summary printed to stdout:
  - Mean / Min / Max / Std for each metric
  - Pass/Fail vs acceptance criteria
"""

import argparse
import csv
import os
import sys
import time
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# ── Import guard for rclpy ──────────────────────────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image, PointCloud2
except ImportError:
    print('[ERROR] rclpy not found. Source the workspace first:')
    print('  source install/setup.bash')
    sys.exit(1)

try:
    import psutil
except ImportError:
    print('[ERROR] psutil not found. Install with: pip install psutil')
    sys.exit(1)

try:
    import statistics
except ImportError:
    pass  # stdlib — always available


# ─────────────────────────────────────────────────────────────────────────────
# Acceptance criteria (Definition of Done for Stage 3)
# ─────────────────────────────────────────────────────────────────────────────
CRITERIA = {
    'color_fps_min':       25.0,   # Hz
    'depth_fps_min':       25.0,   # Hz
    'points_fps_min':      10.0,   # Hz  (PointCloud2 allowed to be lower)
    'color_latency_max_ms': 100.0, # ms
    'depth_latency_max_ms': 100.0, # ms
    'cpu_pct_max':          85.0,  # %   (leave headroom for SLAM/Nav2)
}


@dataclass
class FrameRecord:
    timestamp_s:        float
    color_fps:          float = 0.0
    depth_fps:          float = 0.0
    points_fps:         float = 0.0
    color_latency_ms:   float = 0.0
    depth_latency_ms:   float = 0.0
    points_latency_ms:  float = 0.0
    cpu_pct:            float = 0.0
    ram_mb:             float = 0.0
    color_frames:       int   = 0
    depth_frames:       int   = 0
    points_frames:      int   = 0


class StreamMonitor:
    """Thread-safe per-topic FPS + latency tracker."""

    def __init__(self, window_s: float = 2.0):
        self._window_s    = window_s
        self._stamps      = deque()
        self._lock        = threading.Lock()
        self._last_fps    = 0.0
        self._latency_ms  = 0.0
        self._count       = 0

    def tick(self, header_stamp_s: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._stamps.append(now)
            cutoff = now - self._window_s
            while self._stamps and self._stamps[0] < cutoff:
                self._stamps.popleft()
            n = len(self._stamps)
            self._last_fps   = n / self._window_s if n > 0 else 0.0
            self._latency_ms = (now - header_stamp_s) * 1000.0 \
                               if header_stamp_s > 0.0 else 0.0
            self._count     += 1

    @property
    def fps(self) -> float:
        with self._lock: return self._last_fps

    @property
    def latency_ms(self) -> float:
        with self._lock: return self._latency_ms

    @property
    def count(self) -> int:
        with self._lock: return self._count


class BenchmarkNode(Node):

    def __init__(self, window_s: float = 2.0):
        super().__init__('benchmark_camera_node')

        self._color_mon  = StreamMonitor(window_s)
        self._depth_mon  = StreamMonitor(window_s)
        self._points_mon = StreamMonitor(window_s)

        self.create_subscription(
            Image, '/camera/color/image_raw',      self._cb_color,  10)
        self.create_subscription(
            Image, '/camera/depth/image_rect_raw', self._cb_depth,  10)
        self.create_subscription(
            PointCloud2, '/camera/depth/points',   self._cb_points, 10)

    def _s(self, hdr) -> float:
        try:
            return hdr.stamp.sec + hdr.stamp.nanosec * 1e-9
        except Exception:
            return 0.0

    def _cb_color(self,  msg): self._color_mon.tick(self._s(msg.header))
    def _cb_depth(self,  msg): self._depth_mon.tick(self._s(msg.header))
    def _cb_points(self, msg): self._points_mon.tick(self._s(msg.header))

    def snapshot(self) -> FrameRecord:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.Process().memory_info().rss / 1024 / 1024
        return FrameRecord(
            timestamp_s       = time.monotonic(),
            color_fps         = self._color_mon.fps,
            depth_fps         = self._depth_mon.fps,
            points_fps        = self._points_mon.fps,
            color_latency_ms  = self._color_mon.latency_ms,
            depth_latency_ms  = self._depth_mon.latency_ms,
            points_latency_ms = self._points_mon.latency_ms,
            cpu_pct           = cpu,
            ram_mb            = ram,
            color_frames      = self._color_mon.count,
            depth_frames      = self._depth_mon.count,
            points_frames     = self._points_mon.count,
        )


# ─────────────────────────────────────────────────────────────────────────────

def _col(values, key):
    return [getattr(r, key) for r in values]

def _stat(vals):
    if not vals:
        return 0.0, 0.0, 0.0, 0.0
    return (
        statistics.mean(vals),
        min(vals),
        max(vals),
        statistics.stdev(vals) if len(vals) > 1 else 0.0,
    )

def _pass(val, criterion, lower_is_better=False):
    if lower_is_better:
        return val <= criterion
    return val >= criterion


def run_benchmark(args):
    rclpy.init()
    node = BenchmarkNode(window_s=2.0)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records: list = []
    sample_interval = 0.5  # seconds between snapshots

    print('=' * 62)
    print('  Swachh Boudhik Yantra — D435i Camera Benchmark  (Stage 3)')
    print(f'  Duration : {args.duration}s  |  Warmup: {args.warmup}s')
    print(f'  Output   : {output_path}')
    print('=' * 62)
    print(f'\n[00/{args.duration}s] Warming up ({args.warmup}s) ...')

    start    = time.monotonic()
    warmup   = start + args.warmup
    deadline = start + args.duration

    spinner_thread = threading.Thread(
        target=lambda: rclpy.spin(node), daemon=True)
    spinner_thread.start()

    # ── Warmup ────────────────────────────────────────────────────────────────
    while time.monotonic() < warmup:
        time.sleep(0.5)

    print('[info] Warmup complete. Recording ...\n')

    # ── Recording loop ────────────────────────────────────────────────────────
    while time.monotonic() < deadline:
        rec = node.snapshot()
        records.append(rec)
        elapsed = time.monotonic() - start
        print(
            f'  [{elapsed:5.1f}s]  '
            f'RGB {rec.color_fps:5.1f}Hz  '
            f'Depth {rec.depth_fps:5.1f}Hz  '
            f'PC {rec.points_fps:5.1f}Hz  '
            f'CPU {rec.cpu_pct:4.1f}%  '
            f'RAM {rec.ram_mb:5.1f}MB'
        )
        time.sleep(sample_interval)

    node.destroy_node()
    rclpy.shutdown()

    # ── Write CSV ─────────────────────────────────────────────────────────────
    fieldnames = list(asdict(records[0]).keys())
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))
    print(f'\n[ok] CSV written: {output_path}')

    # ── Summary ───────────────────────────────────────────────────────────────
    print('\n' + '=' * 62)
    print('  BENCHMARK SUMMARY')
    print('=' * 62)

    metrics = [
        ('Color FPS',        'color_fps',         False, CRITERIA['color_fps_min']),
        ('Depth FPS',        'depth_fps',          False, CRITERIA['depth_fps_min']),
        ('Points FPS',       'points_fps',         False, CRITERIA['points_fps_min']),
        ('Color Latency ms', 'color_latency_ms',   True,  CRITERIA['color_latency_max_ms']),
        ('Depth Latency ms', 'depth_latency_ms',   True,  CRITERIA['depth_latency_max_ms']),
        ('CPU %',            'cpu_pct',            True,  CRITERIA['cpu_pct_max']),
    ]

    all_pass = True
    for label, key, lower_better, crit in metrics:
        vals          = _col(records, key)
        mean, mn, mx, sd = _stat(vals)
        passed        = _pass(mean, crit, lower_better)
        all_pass     &= passed
        mark          = 'PASS' if passed else 'FAIL'
        crit_str      = f'{"<=" if lower_better else ">="}{crit}'
        print(
            f'  [{mark}]  {label:<20s}  '
            f'mean={mean:7.2f}  min={mn:7.2f}  max={mx:7.2f}  '
            f'std={sd:5.2f}  criterion={crit_str}'
        )

    total_color  = records[-1].color_frames  if records else 0
    total_depth  = records[-1].depth_frames  if records else 0
    total_points = records[-1].points_frames if records else 0
    print(f'\n  Total frames received during benchmark:')
    print(f'    Color  : {total_color}')
    print(f'    Depth  : {total_depth}')
    print(f'    Points : {total_points}')

    print('\n' + ('  ALL TESTS PASSED ✅' if all_pass else '  SOME TESTS FAILED ❌'))
    print('=' * 62)
    return 0 if all_pass else 1


def main():
    ap = argparse.ArgumentParser(
        description='D435i Camera Benchmark — Stage 3')
    ap.add_argument('--duration',   type=int,   default=60,
                    help='Benchmark duration in seconds (default: 60)')
    ap.add_argument('--warmup',     type=int,   default=5,
                    help='Warmup time in seconds to discard (default: 5)')
    ap.add_argument('--output',     type=str,
                    default=f'bags/stage3/benchmark_{datetime.now():%Y%m%d_%H%M%S}.csv',
                    help='Output CSV file path')
    ap.add_argument('--noise-mode', type=str,   default='ideal',
                    choices=['ideal', 'realistic'],
                    help='Noise mode label stored in CSV filename')
    args = ap.parse_args()

    if args.noise_mode != 'ideal':
        stem = Path(args.output).stem
        args.output = str(Path(args.output).parent / f'{stem}_{args.noise_mode}.csv')

    sys.exit(run_benchmark(args))


if __name__ == '__main__':
    main()

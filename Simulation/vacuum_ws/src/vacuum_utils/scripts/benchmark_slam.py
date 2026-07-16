#!/usr/bin/env python3
"""
benchmark_slam.py  —  Stage 4A: RTAB-Map Performance Benchmark
────────────────────────────────────────────────────────────────
Monitors RTAB-Map performance metrics during a live mapping session
and outputs a CSV + console summary table.

Subscribes:
  /rtabmap/info        → rtabmap_msgs/Info  (keyframes, loop closures,
                          processing time, DB size)
  /rtabmap/map         → nav_msgs/OccupancyGrid (area mapped estimate)
  /odom                → nav_msgs/Odometry (trajectory length)
  /camera/diagnostics  → diagnostic_msgs/DiagnosticArray (FPS metrics)

Publishes:
  nothing (monitoring only)

Outputs (CSV):
  timestamp_s, keyframes, loop_closures, db_size_mb, map_area_m2,
  trajectory_m, rtabmap_update_ms, cpu_pct, ram_mb

Usage:
  # Terminal 1: run sim + SLAM
  ros2 launch vacuum_bringup sim.launch.py world_file:=<path>/apartment.sdf
  ros2 launch vacuum_slam slam.launch.py environment:=apartment

  # Terminal 2: run benchmark (start after SLAM is stable)
  python3.12 src/vacuum_utils/scripts/benchmark_slam.py \
      --duration 300 \
      --environment apartment \
      --output bags/stage4_manual_mapping/apartment/

  # Terminal 3: drive the robot
  ros2 run teleop_twist_keyboard teleop_twist_keyboard

Acceptance criteria (Stage 4A Definition of Done):
  RTAB-Map update time  < 2000ms   (no lag)
  CPU usage             < 85%      (headroom for Nav2 in Stage 5)
  Loop closures         >= 1       (per room traversal)
  DB size growth        < 10MB/min (sustainable for large environments)
"""

import argparse
import csv
import os
import sys
import threading
import time
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

try:
    import rclpy
    from rclpy.node import Node
    from nav_msgs.msg import Odometry, OccupancyGrid
except ImportError:
    print('[ERROR] rclpy not found. Source the workspace first:')
    print('  source install/setup.bash')
    sys.exit(1)

try:
    from rtabmap_msgs.msg import Info as RTABMapInfo
    HAS_RTABMAP_MSGS = True
except ImportError:
    print('[WARN] rtabmap_msgs not found — RTAB-Map stats will be zero.')
    print('       Install: sudo apt-get install -y ros-jazzy-rtabmap-ros')
    HAS_RTABMAP_MSGS = False

try:
    import psutil
except ImportError:
    print('[ERROR] psutil not found. Install: pip install psutil')
    sys.exit(1)


# ── Acceptance criteria ───────────────────────────────────────────────────────
CRITERIA = {
    'rtabmap_update_ms_max': 2000.0,
    'cpu_pct_max':            85.0,
    'loop_closures_min':       1,
    'db_growth_mb_per_min_max': 10.0,
}


@dataclass
class BenchmarkRecord:
    timestamp_s:         float = 0.0
    keyframes:           int   = 0
    loop_closures:       int   = 0
    db_size_mb:          float = 0.0
    map_area_m2:         float = 0.0
    trajectory_m:        float = 0.0
    rtabmap_update_ms:   float = 0.0
    cpu_pct:             float = 0.0
    ram_mb:              float = 0.0


class BenchmarkNode(Node):

    def __init__(self):
        super().__init__('benchmark_slam_node')

        self._lock             = threading.Lock()
        self._keyframes        = 0
        self._loop_closures    = 0
        self._db_size_mb       = 0.0
        self._update_ms        = 0.0
        self._map_area_m2      = 0.0
        self._trajectory_m     = 0.0
        self._prev_x           = None
        self._prev_y           = None

        # Subscribe to RTAB-Map info if available
        if HAS_RTABMAP_MSGS:
            self.create_subscription(
                RTABMapInfo, '/rtabmap/info',
                self._cb_rtabmap_info, 10)

        self.create_subscription(
            OccupancyGrid, '/rtabmap/map',
            self._cb_map, 10)

        self.create_subscription(
            Odometry, '/odom',
            self._cb_odom, 10)

    def _cb_rtabmap_info(self, msg: 'RTABMapInfo') -> None:
        with self._lock:
            self._keyframes     = msg.nodes_count if hasattr(msg, 'nodes_count') else 0
            self._loop_closures = msg.loop_closure_id if hasattr(msg, 'loop_closure_id') else 0
            self._db_size_mb    = msg.database_memory_used if hasattr(msg, 'database_memory_used') else 0
            # Time fields vary by rtabmap version
            if hasattr(msg, 'time_ms'):
                self._update_ms = msg.time_ms
            elif hasattr(msg, 'processing_time_ms'):
                self._update_ms = msg.processing_time_ms

    def _cb_map(self, msg: OccupancyGrid) -> None:
        """Estimate mapped area from free + obstacle cells."""
        resolution = msg.info.resolution
        known_cells = sum(1 for c in msg.data if c >= 0)
        with self._lock:
            self._map_area_m2 = known_cells * (resolution ** 2)

    def _cb_odom(self, msg: Odometry) -> None:
        """Accumulate path length."""
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        with self._lock:
            if self._prev_x is not None:
                dx = x - self._prev_x
                dy = y - self._prev_y
                self._trajectory_m += math.sqrt(dx*dx + dy*dy)
            self._prev_x = x
            self._prev_y = y

    def snapshot(self) -> BenchmarkRecord:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.Process().memory_info().rss / 1024 / 1024
        with self._lock:
            return BenchmarkRecord(
                timestamp_s       = time.monotonic(),
                keyframes         = self._keyframes,
                loop_closures     = self._loop_closures,
                db_size_mb        = self._db_size_mb,
                map_area_m2       = self._map_area_m2,
                trajectory_m      = self._trajectory_m,
                rtabmap_update_ms = self._update_ms,
                cpu_pct           = cpu,
                ram_mb            = ram,
            )


# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark(args):
    rclpy.init()
    node = BenchmarkNode()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f'slam_benchmark_{args.environment}_{datetime.now():%Y%m%d_%H%M%S}.csv'

    records = []
    sample_interval = 1.0

    print('=' * 66)
    print(f'  Swachh Boudhik Yantra — SLAM Benchmark  (Stage 4A)')
    print(f'  Environment : {args.environment}')
    print(f'  Duration    : {args.duration}s   Warmup: {args.warmup}s')
    print(f'  Output      : {csv_path}')
    print('=' * 66)
    print()

    start    = time.monotonic()
    warmup   = start + args.warmup
    deadline = start + args.duration

    spinner = threading.Thread(target=lambda: rclpy.spin(node), daemon=True)
    spinner.start()

    print(f'Warming up ({args.warmup}s)...')
    while time.monotonic() < warmup:
        time.sleep(0.5)
    print('Recording...\n')

    header = ('  {:>6}  {:>6}  {:>5}  {:>6}  {:>8}  {:>7}  {:>8}  {:>5}  {:>6}'
              .format('t(s)', 'KF', 'LC', 'DB_MB', 'Area_m2',
                      'Path_m', 'Upd_ms', 'CPU%', 'RAM_MB'))
    print(header)
    print('  ' + '-' * 70)

    while time.monotonic() < deadline:
        rec = node.snapshot()
        records.append(rec)
        elapsed = time.monotonic() - start
        print(
            f'  {elapsed:6.1f}  {rec.keyframes:6d}  {rec.loop_closures:5d}  '
            f'{rec.db_size_mb:6.1f}  {rec.map_area_m2:8.2f}  '
            f'{rec.trajectory_m:7.2f}  {rec.rtabmap_update_ms:8.1f}  '
            f'{rec.cpu_pct:5.1f}  {rec.ram_mb:6.1f}'
        )
        time.sleep(sample_interval)

    node.destroy_node()
    rclpy.shutdown()

    # ── Write CSV ─────────────────────────────────────────────────────────
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(records[0]).keys()))
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))
    print(f'\n[ok] CSV: {csv_path}')

    # ── Summary ───────────────────────────────────────────────────────────
    if not records:
        print('[warn] No data recorded.')
        return 1

    last     = records[-1]
    first    = records[0]

    def _mean(key):
        vals = [getattr(r, key) for r in records]
        return sum(vals) / len(vals) if vals else 0.0

    db_growth = (last.db_size_mb - first.db_size_mb)
    duration  = (last.timestamp_s - first.timestamp_s) / 60.0   # minutes
    db_per_min = db_growth / duration if duration > 0 else 0.0

    pass_update = _mean('rtabmap_update_ms') <= CRITERIA['rtabmap_update_ms_max']
    pass_cpu    = _mean('cpu_pct')           <= CRITERIA['cpu_pct_max']
    pass_lc     = last.loop_closures         >= CRITERIA['loop_closures_min']
    pass_db     = db_per_min                 <= CRITERIA['db_growth_mb_per_min_max']

    print('\n' + '=' * 66)
    print('  SLAM BENCHMARK SUMMARY')
    print('=' * 66)
    print(f'  Environment    : {args.environment}')
    print(f'  Duration       : {duration*60:.0f}s')
    print(f'  Total keyframes: {last.keyframes}')
    print(f'  Loop closures  : {last.loop_closures}  '
          f'(criterion: >={CRITERIA["loop_closures_min"]})  '
          f'{"PASS" if pass_lc else "FAIL"}')
    print(f'  Map area       : {last.map_area_m2:.2f} m²')
    print(f'  Trajectory     : {last.trajectory_m:.2f} m')
    print(f'  DB size        : {last.db_size_mb:.1f} MB')
    print(f'  DB growth      : {db_per_min:.2f} MB/min  '
          f'(criterion: <={CRITERIA["db_growth_mb_per_min_max"]})  '
          f'{"PASS" if pass_db else "FAIL"}')
    print(f'  RTAB update ms : {_mean("rtabmap_update_ms"):.1f}ms  '
          f'(criterion: <={CRITERIA["rtabmap_update_ms_max"]})  '
          f'{"PASS" if pass_update else "FAIL"}')
    print(f'  CPU %          : {_mean("cpu_pct"):.1f}%  '
          f'(criterion: <={CRITERIA["cpu_pct_max"]}%)  '
          f'{"PASS" if pass_cpu else "FAIL"}')
    print(f'  RAM            : {_mean("ram_mb"):.0f} MB (avg)')

    all_pass = pass_update and pass_cpu and pass_lc and pass_db
    print()
    print('  ' + ('ALL PASS ✅' if all_pass else 'SOME FAILED ❌'))
    print('=' * 66)
    return 0 if all_pass else 1


def main():
    ap = argparse.ArgumentParser(
        description='SLAM Performance Benchmark — Stage 4A')
    ap.add_argument('--duration',    type=int, default=300,
                    help='Benchmark duration in seconds (default: 300)')
    ap.add_argument('--warmup',      type=int, default=10,
                    help='Warmup seconds to discard (default: 10)')
    ap.add_argument('--environment', type=str, default='room',
                    help='Environment label for CSV naming')
    ap.add_argument('--output',      type=str,
                    default='bags/stage4_manual_mapping',
                    help='Output directory for CSV files')
    args = ap.parse_args()

    sys.exit(run_benchmark(args))


if __name__ == '__main__':
    main()

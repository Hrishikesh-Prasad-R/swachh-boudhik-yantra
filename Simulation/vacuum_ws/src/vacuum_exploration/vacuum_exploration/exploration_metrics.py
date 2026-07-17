#!/usr/bin/env python3.12
"""
exploration_metrics.py  —  Stage 4B: Research Metrics Collector
────────────────────────────────────────────────────────────────
Collects and logs quantitative metrics throughout the exploration run.

Metrics logged (1 Hz CSV):
  timestamp_sec, state, frontiers_count, goals_sent, goals_succeeded,
  goals_failed, distance_traveled_m, coverage_pct, free_cells,
  unknown_cells, cpu_pct, ram_mb, elapsed_sec

Coverage formula:
  coverage_pct = free_cells / (free_cells + unknown_cells) * 100

At exploration completion (FINISHED state), produces:
  1. Final summary printed to console
  2. metadata.yaml alongside the CSV with run reproducibility info

Output structure:
  ~/bags/stage4b/<environment>/run_<N>/
    metrics.csv
    metadata.yaml

Parameters (from exploration_params.yaml):
  output_base_dir   — base path for output
  log_rate          — Hz (rows per second)
"""

import csv
import json
import math
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy

from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import String

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────

class ExplorationMetrics(Node):

    def __init__(self):
        super().__init__('exploration_metrics')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('output_base_dir', '~/bags/stage4b')
        self.declare_parameter('log_rate', 1.0)
        self.declare_parameter('environment', 'apartment')
        self.declare_parameter('nav2_config', 'nav2_params.yaml')
        self.declare_parameter('exploration_config', 'exploration_params.yaml')

        p = lambda n: self.get_parameter(n).value
        output_base  = os.path.expanduser(p('output_base_dir'))
        self._env    = p('environment')
        log_rate     = p('log_rate')
        self._nav2_config = p('nav2_config')
        self._exp_config  = p('exploration_config')

        # ── Output directory (auto-numbered run) ──────────────────────────────
        env_dir = Path(output_base) / self._env
        env_dir.mkdir(parents=True, exist_ok=True)
        run_num = self._next_run_number(env_dir)
        self._run_dir = env_dir / f'run_{run_num:02d}'
        self._run_dir.mkdir(parents=True, exist_ok=True)

        self._csv_path  = self._run_dir / 'metrics.csv'
        self._meta_path = self._run_dir / 'metadata.yaml'

        # ── CSV setup ─────────────────────────────────────────────────────────
        self._csv_file = open(self._csv_path, 'w', newline='')
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            'timestamp_sec', 'state', 'frontiers_count',
            'goals_sent', 'goals_succeeded', 'goals_failed',
            'distance_traveled_m', 'coverage_pct', 'free_cells',
            'unknown_cells', 'cpu_pct', 'ram_mb', 'elapsed_sec',
        ])
        self._csv_file.flush()

        # ── State ─────────────────────────────────────────────────────────────
        self._start_time    = self.get_clock().now().nanoseconds / 1e9
        self._last_status   = {}
        self._distance      = 0.0
        self._last_x: float | None = None
        self._last_y: float | None = None
        self._last_map: OccupancyGrid | None = None
        self._finished_logged = False

        # ── Subscriptions ─────────────────────────────────────────────────────
        map_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            depth=1,
        )
        self.create_subscription(String, '/exploration/status', self._status_cb, 10)
        self.create_subscription(OccupancyGrid, '/rtabmap/map', self._map_cb, map_qos)
        self.create_subscription(Odometry, '/odom', self._odom_cb, 10)

        # ── Logging timer ─────────────────────────────────────────────────────
        self.create_timer(1.0 / log_rate, self._log_row)

        self.get_logger().info(
            f'ExplorationMetrics | run={run_num} | dir={self._run_dir}'
        )

        # Write metadata immediately (updated at finish)
        self._write_metadata(complete=False)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _status_cb(self, msg: String) -> None:
        try:
            self._last_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _map_cb(self, msg: OccupancyGrid) -> None:
        self._last_map = msg

    def _odom_cb(self, msg: Odometry) -> None:
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        if self._last_x is not None:
            self._distance += math.hypot(x - self._last_x, y - self._last_y)
        self._last_x = x
        self._last_y = y

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log_row(self) -> None:
        now = self.get_clock().now().nanoseconds / 1e9
        elapsed = now - self._start_time

        # Coverage
        free_cells = unknown_cells = 0
        coverage_pct = 0.0
        if self._last_map is not None:
            for v in self._last_map.data:
                if v == 0:
                    free_cells += 1
                elif v == -1:
                    unknown_cells += 1
            total = free_cells + unknown_cells
            if total > 0:
                coverage_pct = (free_cells / total) * 100.0

        # System resources
        cpu_pct = ram_mb = 0.0
        if PSUTIL_AVAILABLE:
            cpu_pct = psutil.cpu_percent(interval=None)
            ram_mb  = psutil.virtual_memory().used / 1e6

        # Status fields (from exploration_manager)
        s = self._last_status
        state           = s.get('state', 'UNKNOWN')
        frontiers_count = s.get('frontiers_remaining', 0)
        goals_sent      = s.get('goals_completed', 0) + s.get('goals_failed', 0)
        goals_succeeded = s.get('goals_completed', 0)
        goals_failed    = s.get('goals_failed', 0)

        self._csv_writer.writerow([
            f'{now:.3f}', state, frontiers_count,
            goals_sent, goals_succeeded, goals_failed,
            f'{self._distance:.3f}', f'{coverage_pct:.2f}',
            free_cells, unknown_cells,
            f'{cpu_pct:.1f}', f'{ram_mb:.1f}', f'{elapsed:.1f}',
        ])
        self._csv_file.flush()

        # Detect finished state and write final summary once
        if state == 'FINISHED' and not self._finished_logged:
            self._finished_logged = True
            self._write_summary(elapsed, coverage_pct, free_cells, goals_succeeded, goals_failed)
            self._write_metadata(complete=True)
            self._csv_file.close()

    # ── Final summary ─────────────────────────────────────────────────────────

    def _write_summary(
        self, elapsed: float, coverage_pct: float,
        free_cells: int, succeeded: int, failed: int
    ) -> None:
        summary_path = self._run_dir / 'summary.txt'
        lines = [
            '═══════════════════════════════════════════════════',
            '  Stage 4B Exploration — Run Summary',
            '═══════════════════════════════════════════════════',
            f'  Environment   : {self._env}',
            f'  Elapsed time  : {elapsed:.1f} s  ({elapsed/60:.1f} min)',
            f'  Coverage      : {coverage_pct:.2f} %',
            f'  Free cells    : {free_cells}',
            f'  Distance      : {self._distance:.2f} m',
            f'  Goals OK      : {succeeded}',
            f'  Goals failed  : {failed}',
            f'  Success rate  : {100*succeeded/(succeeded+failed):.1f} %'
            if (succeeded + failed) > 0 else '  Success rate  : N/A',
            '═══════════════════════════════════════════════════',
            f'  Metrics CSV   : {self._csv_path}',
            f'  Metadata YAML : {self._meta_path}',
            '═══════════════════════════════════════════════════',
        ]
        text = '\n'.join(lines)
        self.get_logger().info(text)
        summary_path.write_text(text + '\n')

    def _write_metadata(self, complete: bool) -> None:
        """Write a YAML metadata file for reproducibility."""
        git_commit = 'unknown'
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, timeout=3,
                cwd=os.path.expanduser('~/Swachh_Boudhik_Yantra'),
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip()
        except Exception:
            pass

        rtabmap_db = os.path.expanduser('~/.ros/rtabmap.db')

        content = (
            f'# Exploration run metadata — generated automatically\n'
            f'environment:       {self._env}\n'
            f'run_dir:           {self._run_dir}\n'
            f'started_at:        {datetime.utcnow().isoformat()}Z\n'
            f'complete:          {complete}\n'
            f'git_commit:        {git_commit}\n'
            f'nav2_config:       {self._nav2_config}\n'
            f'exploration_config:{self._exp_config}\n'
            f'rtabmap_db:        {rtabmap_db}\n'
            f'metrics_csv:       {self._csv_path}\n'
            f'psutil_available:  {PSUTIL_AVAILABLE}\n'
        )
        self._meta_path.write_text(content)

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _next_run_number(env_dir: Path) -> int:
        """Find the next available run_N directory number."""
        existing = [
            int(d.name.split('_')[1])
            for d in env_dir.iterdir()
            if d.is_dir() and d.name.startswith('run_')
        ]
        return (max(existing) + 1) if existing else 1


# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = ExplorationMetrics()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if not node._csv_file.closed:
            node._csv_file.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

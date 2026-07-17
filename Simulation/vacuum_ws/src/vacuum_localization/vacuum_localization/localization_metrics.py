#!/usr/bin/env python3.12
"""
localization_metrics.py  —  Stage 5: Localization & Navigation Metrics
────────────────────────────────────────────────────────────────────────
1 Hz CSV logging of localization quality and navigation statistics.

CSV columns:
  timestamp_sec, loc_state, cov_trace, yaw_variance, particle_count,
  goals_sent, goals_succeeded, goals_failed, distance_m,
  recoveries, cpu_pct, ram_mb, elapsed_sec

Output structure:
  ~/bags/stage5/<environment>/run_<N>/
    localization.csv
    metadata.yaml
    summary.txt (on shutdown)

Parameters (localization_params.yaml):
  output_base_dir, log_rate, environment, map_file
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
from rclpy.qos import QoSReliabilityPolicy, QoSProfile

from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String

from .pose_quality import PoseQuality

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class LocalizationMetrics(Node):

    def __init__(self):
        super().__init__('localization_metrics')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('output_base_dir', '~/bags/stage5')
        self.declare_parameter('log_rate',        1.0)
        self.declare_parameter('environment',     'apartment')
        self.declare_parameter('map_file',        '')

        p = lambda n: self.get_parameter(n).value
        output_base  = os.path.expanduser(p('output_base_dir'))
        self._env    = p('environment')
        log_rate     = p('log_rate')
        self._map_file = p('map_file')

        # ── Output directory ──────────────────────────────────────────────────
        env_dir = Path(output_base) / self._env
        env_dir.mkdir(parents=True, exist_ok=True)
        run_num = self._next_run_number(env_dir)
        self._run_dir = env_dir / f'run_{run_num:02d}'
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._csv_path  = self._run_dir / 'localization.csv'
        self._meta_path = self._run_dir / 'metadata.yaml'

        # ── CSV ───────────────────────────────────────────────────────────────
        self._csv_file   = open(self._csv_path, 'w', newline='')
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            'timestamp_sec', 'loc_state', 'cov_trace', 'yaw_variance',
            'particle_count', 'goals_sent', 'goals_succeeded', 'goals_failed',
            'distance_m', 'recoveries', 'cpu_pct', 'ram_mb', 'elapsed_sec',
        ])
        self._csv_file.flush()

        # ── State ─────────────────────────────────────────────────────────────
        self._start_time   = self.get_clock().now().nanoseconds / 1e9
        self._last_status  = {}
        self._last_recovery = {}
        self._last_cov: list  = []
        self._distance        = 0.0
        self._recoveries      = 0
        self._last_x: float | None = None
        self._last_y: float | None = None
        self._qual = PoseQuality()

        # ── Subscriptions ─────────────────────────────────────────────────────
        best_effort = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT, depth=10)

        self.create_subscription(
            String, '/localization/status', self._status_cb, 10)
        self.create_subscription(
            String, '/localization/recovery_status', self._recovery_cb, 10)
        self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._amcl_cb, best_effort)
        self.create_subscription(
            Odometry, '/odom', self._odom_cb, 10)

        # ── Timer ─────────────────────────────────────────────────────────────
        self.create_timer(1.0 / log_rate, self._log_row)

        self._write_metadata(complete=False)
        self.get_logger().info(
            f'LocalizationMetrics | run={run_num} | dir={self._run_dir}')

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _status_cb(self, msg: String) -> None:
        try:
            self._last_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _recovery_cb(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            if data.get('result', '').startswith('ATTEMPT'):
                self._recoveries += 1
        except json.JSONDecodeError:
            pass

    def _amcl_cb(self, msg: PoseWithCovarianceStamped) -> None:
        self._last_cov = list(msg.pose.covariance)

    def _odom_cb(self, msg: Odometry) -> None:
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        if self._last_x is not None:
            self._distance += math.hypot(x - self._last_x, y - self._last_y)
        self._last_x = x
        self._last_y = y

    # ── CSV row ───────────────────────────────────────────────────────────────

    def _log_row(self) -> None:
        now     = self.get_clock().now().nanoseconds / 1e9
        elapsed = now - self._start_time

        cov_trace   = self._qual.trace_position(self._last_cov) if self._last_cov else -1.0
        yaw_var     = self._qual.yaw_variance(self._last_cov)   if self._last_cov else -1.0

        s = self._last_status
        loc_state       = s.get('state', 'UNKNOWN')
        particle_count  = s.get('particle_count', 0)

        cpu_pct = ram_mb = 0.0
        if PSUTIL_AVAILABLE:
            cpu_pct = psutil.cpu_percent(interval=None)
            ram_mb  = psutil.virtual_memory().used / 1e6

        self._csv_writer.writerow([
            f'{now:.3f}', loc_state, f'{cov_trace:.5f}', f'{yaw_var:.5f}',
            particle_count, 0, 0, 0,   # goals logged by external nav node
            f'{self._distance:.3f}', self._recoveries,
            f'{cpu_pct:.1f}', f'{ram_mb:.1f}', f'{elapsed:.1f}',
        ])
        self._csv_file.flush()

    # ── Metadata ──────────────────────────────────────────────────────────────

    def _write_metadata(self, complete: bool) -> None:
        git_commit = 'unknown'
        try:
            r = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, timeout=3,
                cwd=os.path.expanduser('~/Swachh_Boudhik_Yantra'),
            )
            if r.returncode == 0:
                git_commit = r.stdout.strip()
        except Exception:
            pass

        content = (
            f'# Stage 5 localization metrics metadata\n'
            f'environment:   {self._env}\n'
            f'run_dir:       {self._run_dir}\n'
            f'started_at:    {datetime.utcnow().isoformat()}Z\n'
            f'complete:      {complete}\n'
            f'git_commit:    {git_commit}\n'
            f'map_file:      {self._map_file}\n'
            f'csv:           {self._csv_path}\n'
            f'psutil:        {PSUTIL_AVAILABLE}\n'
        )
        self._meta_path.write_text(content)

    @staticmethod
    def _next_run_number(env_dir: Path) -> int:
        existing = [
            int(d.name.split('_')[1])
            for d in env_dir.iterdir()
            if d.is_dir() and d.name.startswith('run_')
        ]
        return (max(existing) + 1) if existing else 1

    def destroy_node(self):
        if not self._csv_file.closed:
            self._csv_file.close()
        self._write_metadata(complete=True)
        super().destroy_node()


# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = LocalizationMetrics()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

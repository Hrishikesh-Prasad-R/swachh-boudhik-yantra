#!/usr/bin/env python3
"""
collect_metrics.py
──────────────────
Stage 1 system metrics collector.

Collects and logs:
  - CPU usage (%) — overall and per-core
  - RAM usage (MB and %)
  - ROS2 process memory breakdown
  - TF publication frequency on /tf
  - Odometry frequency on /odom
  - Joint state frequency on /joint_states

Writes a timestamped CSV to ~/paper_ws/results/stage1/ by default.

Usage:
  # While simulation is running in another terminal:
  python3 collect_metrics.py --duration 60 --output /tmp/stage1_metrics.csv
  ros2 run vacuum_utils collect_metrics.py --duration 30
"""

import os
import sys
import csv
import time
import signal
import argparse
import threading
from datetime import datetime
from collections import deque

import rclpy
from rclpy.node import Node
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print('[WARN] psutil not installed. Install with: pip3 install psutil')
    print('       CPU/RAM metrics will be skipped.')


class MetricsCollector(Node):
    """
    Collects system and ROS topic metrics at 1 Hz.
    """

    def __init__(self, duration_s: int, output_file: str):
        super().__init__('vacuum_metrics_collector')

        self.duration_s    = duration_s
        self.output_file   = output_file
        self.start_time    = time.time()
        self.records       = []
        self._shutdown     = threading.Event()

        # Topic frequency tracking (sliding 1s window)
        self._tf_times     = deque(maxlen=100)
        self._odom_times   = deque(maxlen=100)
        self._joint_times  = deque(maxlen=100)

        # Subscriptions
        self.create_subscription(TFMessage,   '/tf',          self._tf_cb,    10)
        self.create_subscription(Odometry,    '/odom',        self._odom_cb,  10)
        self.create_subscription(JointState,  '/joint_states', self._joint_cb, 10)

        # Metric collection timer at 1 Hz
        self.create_timer(1.0, self._collect)

        self.get_logger().info(
            f'Collecting metrics for {duration_s}s → {output_file}')
        print(f'\n{"Time":>6}  {"CPU%":>6}  {"RAM_MB":>8}  '
              f'{"TF_Hz":>7}  {"Odom_Hz":>8}  {"Joints_Hz":>10}')
        print('-' * 60)

    # ── Topic callbacks ────────────────────────────────────────────
    def _tf_cb(self, _):
        self._tf_times.append(time.time())

    def _odom_cb(self, _):
        self._odom_times.append(time.time())

    def _joint_cb(self, _):
        self._joint_times.append(time.time())

    # ── Helper: topic frequency (messages in last 1 s) ─────────────
    @staticmethod
    def _freq(times: deque) -> float:
        now = time.time()
        recent = [t for t in times if now - t <= 1.0]
        return float(len(recent))

    # ── Metric collection callback ─────────────────────────────────
    def _collect(self):
        elapsed = time.time() - self.start_time

        # System metrics
        cpu_pct   = psutil.cpu_percent(interval=None) if HAS_PSUTIL else -1.0
        ram_mb    = (psutil.virtual_memory().used / 1e6) if HAS_PSUTIL else -1.0
        ram_pct   = psutil.virtual_memory().percent if HAS_PSUTIL else -1.0

        # Topic frequencies
        tf_hz    = self._freq(self._tf_times)
        odom_hz  = self._freq(self._odom_times)
        joint_hz = self._freq(self._joint_times)

        record = {
            'time_s':    round(elapsed, 1),
            'cpu_pct':   round(cpu_pct, 1),
            'ram_mb':    round(ram_mb, 1),
            'ram_pct':   round(ram_pct, 1),
            'tf_hz':     round(tf_hz, 1),
            'odom_hz':   round(odom_hz, 1),
            'joint_hz':  round(joint_hz, 1),
        }
        self.records.append(record)

        print(f'{elapsed:6.1f}  {cpu_pct:6.1f}  {ram_mb:8.1f}  '
              f'{tf_hz:7.1f}  {odom_hz:8.1f}  {joint_hz:10.1f}')

        if elapsed >= self.duration_s:
            self._finish()

    def _finish(self):
        """Write CSV and print summary."""
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        with open(self.output_file, 'w', newline='') as f:
            if self.records:
                writer = csv.DictWriter(f, fieldnames=self.records[0].keys())
                writer.writeheader()
                writer.writerows(self.records)

        # Summary
        if self.records:
            cpu_vals  = [r['cpu_pct'] for r in self.records if r['cpu_pct'] >= 0]
            ram_vals  = [r['ram_mb']  for r in self.records if r['ram_mb']  >= 0]
            tf_vals   = [r['tf_hz']   for r in self.records]
            odom_vals = [r['odom_hz'] for r in self.records]

            print('\n' + '═' * 60)
            print('  Stage 1 Metrics Summary')
            print('═' * 60)
            print(f'  Duration:      {self.records[-1]["time_s"]:.1f} s')
            if cpu_vals:
                print(f'  CPU mean:      {sum(cpu_vals)/len(cpu_vals):.1f}%')
                print(f'  CPU max:       {max(cpu_vals):.1f}%')
            if ram_vals:
                print(f'  RAM mean:      {sum(ram_vals)/len(ram_vals):.1f} MB')
                print(f'  RAM max:       {max(ram_vals):.1f} MB')
            if tf_vals:
                print(f'  TF Hz mean:    {sum(tf_vals)/len(tf_vals):.1f}')
            if odom_vals:
                print(f'  Odom Hz mean:  {sum(odom_vals)/len(odom_vals):.1f}')
            print(f'\n  Output saved:  {self.output_file}')
            print('═' * 60)

        self._shutdown.set()


def main(args=None):
    parser = argparse.ArgumentParser(description='Collect Stage 1 metrics')
    parser.add_argument('--duration', type=int, default=60,
                        help='Collection duration in seconds (default: 60)')
    parser.add_argument('--output', type=str,
                        default=os.path.expanduser(
                            f'~/paper_ws/results/stage1/metrics_'
                            f'{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'),
                        help='Output CSV file path')
    parsed, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    collector = MetricsCollector(
        duration_s=parsed.duration,
        output_file=parsed.output)

    # Spin until done
    while not collector._shutdown.is_set():
        rclpy.spin_once(collector, timeout_sec=0.1)

    collector.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

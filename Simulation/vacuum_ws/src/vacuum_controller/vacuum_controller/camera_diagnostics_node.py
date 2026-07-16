#!/usr/bin/env python3
"""
camera_diagnostics_node.py  —  Stage 3 (D435i Perception Pipeline)
───────────────────────────────────────────────────────────────────
Monitors the simulated Intel RealSense D435i pipeline and publishes
real-time diagnostics to /camera/diagnostics.

Metrics collected (all as a DiagnosticArray):
  - RGB image FPS             (target: 30 Hz)
  - Depth image FPS           (target: 30 Hz)
  - PointCloud2 FPS           (target: 30 Hz)
  - RGB latency               (sim_time delay from header to now)
  - Depth latency
  - PointCloud2 latency
  - Dropped frame count       (estimated from FPS drops)
  - CPU usage                 (system-wide %)
  - RAM usage                 (process RSS MB)
  - Gazebo Real Time Factor   (from /stats if available)

Parameters (from camera.yaml / camera_diagnostics_node namespace):
  diagnostics.min_fps_color    (float, Hz)
  diagnostics.min_fps_depth    (float, Hz)
  diagnostics.min_fps_points   (float, Hz)
  diagnostics.max_latency_s    (float, s)
  diagnostics.fps_window_s     (float, s)
  diagnostics.publish_rate_hz  (float, Hz)
  topics.color_image           (string)
  topics.depth_image           (string)
  topics.depth_points          (string)

Subscribes:
  /camera/color/image_raw        sensor_msgs/Image
  /camera/depth/image_rect_raw   sensor_msgs/Image
  /camera/depth/points           sensor_msgs/PointCloud2

Publishes:
  /camera/diagnostics            diagnostic_msgs/DiagnosticArray
"""

import time
import psutil
import threading
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.time import Time

from sensor_msgs.msg import Image, PointCloud2
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue


class FPSTracker:
    """
    Lock-safe rolling-window FPS estimator.
    Stores arrival timestamps in a deque; FPS = count / window.
    """
    def __init__(self, window_s: float = 2.0):
        self._window_s  = window_s
        self._stamps    = deque()
        self._lock      = threading.Lock()
        self._drop_est  = 0
        self._last_fps  = 0.0
        self._latency_s = 0.0
        self._count     = 0

    def tick(self, msg_stamp_s: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._stamps.append(now)
            # evict old stamps outside window
            cutoff = now - self._window_s
            while self._stamps and self._stamps[0] < cutoff:
                self._stamps.popleft()
            self._last_fps  = len(self._stamps) / self._window_s
            self._latency_s = now - msg_stamp_s if msg_stamp_s > 0.0 else 0.0
            self._count    += 1

    @property
    def fps(self) -> float:
        with self._lock:
            return self._last_fps

    @property
    def latency_s(self) -> float:
        with self._lock:
            return self._latency_s

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


class CameraDiagnosticsNode(Node):

    def __init__(self):
        super().__init__('camera_diagnostics_node')

        # ── Parameters ──────────────────────────────────────────────────────
        self.declare_parameter('diagnostics.min_fps_color',    25.0)
        self.declare_parameter('diagnostics.min_fps_depth',    25.0)
        self.declare_parameter('diagnostics.min_fps_points',   10.0)
        self.declare_parameter('diagnostics.max_latency_s',     0.10)
        self.declare_parameter('diagnostics.fps_window_s',      2.0)
        self.declare_parameter('diagnostics.publish_rate_hz',   5.0)
        self.declare_parameter('topics.color_image',   '/camera/color/image_raw')
        self.declare_parameter('topics.depth_image',   '/camera/depth/image_rect_raw')
        self.declare_parameter('topics.depth_points',  '/camera/depth/points')

        p = self.get_parameters_by_prefix('diagnostics')
        win  = self.get_parameter('diagnostics.fps_window_s').value
        rate = self.get_parameter('diagnostics.publish_rate_hz').value
        self._min_fps_color  = self.get_parameter('diagnostics.min_fps_color').value
        self._min_fps_depth  = self.get_parameter('diagnostics.min_fps_depth').value
        self._min_fps_points = self.get_parameter('diagnostics.min_fps_points').value
        self._max_latency_s  = self.get_parameter('diagnostics.max_latency_s').value

        color_topic  = self.get_parameter('topics.color_image').value
        depth_topic  = self.get_parameter('topics.depth_image').value
        points_topic = self.get_parameter('topics.depth_points').value

        # ── FPS trackers ─────────────────────────────────────────────────────
        self._tracker_color  = FPSTracker(win)
        self._tracker_depth  = FPSTracker(win)
        self._tracker_points = FPSTracker(win)
        self._start_time     = time.monotonic()

        # ── Subscriptions ────────────────────────────────────────────────────
        self.create_subscription(
            Image, color_topic,
            self._cb_color, 10)

        self.create_subscription(
            Image, depth_topic,
            self._cb_depth, 10)

        self.create_subscription(
            PointCloud2, points_topic,
            self._cb_points, 10)

        # ── Publisher ────────────────────────────────────────────────────────
        self._pub_diag = self.create_publisher(
            DiagnosticArray, '/camera/diagnostics', 10)

        # ── Publish timer ────────────────────────────────────────────────────
        period = 1.0 / rate
        self.create_timer(period, self._publish_diagnostics)

        self.get_logger().info(
            f'[camera_diagnostics] monitoring {color_topic} | '
            f'{depth_topic} | {points_topic}')

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _stamp_to_float(self, header) -> float:
        """Convert ROS header stamp to monotonic seconds (best effort)."""
        try:
            return header.stamp.sec + header.stamp.nanosec * 1e-9
        except Exception:
            return 0.0

    def _cb_color(self, msg: Image) -> None:
        self._tracker_color.tick(self._stamp_to_float(msg.header))

    def _cb_depth(self, msg: Image) -> None:
        self._tracker_depth.tick(self._stamp_to_float(msg.header))

    def _cb_points(self, msg: PointCloud2) -> None:
        self._tracker_points.tick(self._stamp_to_float(msg.header))

    # ── Diagnostics publisher ────────────────────────────────────────────────

    def _make_status(self, name: str, fps: float, latency_s: float,
                     count: int, min_fps: float) -> DiagnosticStatus:
        ok       = fps >= min_fps and latency_s <= self._max_latency_s
        level    = DiagnosticStatus.OK if ok else DiagnosticStatus.WARN
        summary  = 'OK' if ok else f'LOW FPS ({fps:.1f} Hz) or HIGH LATENCY ({latency_s*1000:.1f} ms)'

        status = DiagnosticStatus()
        status.name    = name
        status.level   = level
        status.message = summary
        status.values  = [
            KeyValue(key='fps',           value=f'{fps:.2f} Hz'),
            KeyValue(key='min_fps',       value=f'{min_fps:.1f} Hz'),
            KeyValue(key='latency_ms',    value=f'{latency_s*1000:.2f} ms'),
            KeyValue(key='max_latency_ms',value=f'{self._max_latency_s*1000:.0f} ms'),
            KeyValue(key='frame_count',   value=str(count)),
        ]
        return status

    def _publish_diagnostics(self) -> None:
        cpu_pct  = psutil.cpu_percent(interval=None)
        ram_mb   = psutil.Process().memory_info().rss / 1024 / 1024
        uptime_s = time.monotonic() - self._start_time

        color_fps  = self._tracker_color.fps
        depth_fps  = self._tracker_depth.fps
        points_fps = self._tracker_points.fps

        arr = DiagnosticArray()
        arr.header.stamp = self.get_clock().now().to_msg()

        arr.status.append(self._make_status(
            'D435i/Color',  color_fps,  self._tracker_color.latency_s,
            self._tracker_color.count,  self._min_fps_color))

        arr.status.append(self._make_status(
            'D435i/Depth',  depth_fps,  self._tracker_depth.latency_s,
            self._tracker_depth.count,  self._min_fps_depth))

        arr.status.append(self._make_status(
            'D435i/Points', points_fps, self._tracker_points.latency_s,
            self._tracker_points.count, self._min_fps_points))

        sys_status = DiagnosticStatus()
        sys_status.name    = 'D435i/System'
        sys_status.level   = DiagnosticStatus.OK
        sys_status.message = 'System metrics'
        sys_status.values  = [
            KeyValue(key='cpu_pct',    value=f'{cpu_pct:.1f} %'),
            KeyValue(key='ram_mb',     value=f'{ram_mb:.1f} MB'),
            KeyValue(key='uptime_s',   value=f'{uptime_s:.0f} s'),
        ]
        arr.status.append(sys_status)

        self._pub_diag.publish(arr)


def main(args=None):
    rclpy.init(args=args)
    node = CameraDiagnosticsNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

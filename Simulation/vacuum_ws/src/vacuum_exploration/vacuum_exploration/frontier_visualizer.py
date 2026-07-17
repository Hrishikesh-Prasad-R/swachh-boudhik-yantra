#!/usr/bin/env python3.12
"""
frontier_visualizer.py  —  Stage 4B: RViz Visualisation
─────────────────────────────────────────────────────────
Subscribes to exploration topics and publishes rich RViz markers.

Marker channels:
  /frontiers/markers          (green spheres)  — all detected frontiers
  /exploration/selected_marker (red sphere)    — current target frontier
  /exploration/goal_marker     (yellow arrow)  — Nav2 goal pose
  /exploration/trajectory      (blue line)     — robot path history
  /exploration/status_text     (white text)    — FSM state overlay

These markers are additive — the visualizer does not duplicate what the
frontier_detector already publishes. It adds the trajectory and text overlays.

Parameters: uses /odom and /exploration/current_goal subscriptions.
"""

import json
from collections import deque
from typing import Deque

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Point, PoseStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import ColorRGBA, Header, String
from visualization_msgs.msg import Marker, MarkerArray


class FrontierVisualizer(Node):

    # Trajectory history length (metres of points)
    MAX_TRAJECTORY_POINTS = 2000

    def __init__(self):
        super().__init__('frontier_visualizer')

        # ── State ─────────────────────────────────────────────────────────────
        self._trajectory: Deque[Point] = deque(maxlen=self.MAX_TRAJECTORY_POINTS)
        self._last_status: dict = {}
        self._current_goal: PoseStamped | None = None

        # ── Subscriptions ─────────────────────────────────────────────────────
        self.create_subscription(Odometry,     '/odom',                     self._odom_cb,   10)
        self.create_subscription(String,       '/exploration/status',        self._status_cb, 10)
        self.create_subscription(PoseStamped,  '/exploration/current_goal', self._goal_cb,   10)

        # ── Publishers ────────────────────────────────────────────────────────
        self._goal_marker_pub = self.create_publisher(
            MarkerArray, '/exploration/goal_marker', 10)
        self._trajectory_pub = self.create_publisher(
            Marker, '/exploration/trajectory', 10)
        self._text_pub = self.create_publisher(
            Marker, '/exploration/status_text', 10)

        # ── Publish timer (4 Hz) ──────────────────────────────────────────────
        self.create_timer(0.25, self._publish_all)

        self.get_logger().info('FrontierVisualizer ready.')

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _odom_cb(self, msg: Odometry) -> None:
        p = Point()
        p.x = msg.pose.pose.position.x
        p.y = msg.pose.pose.position.y
        p.z = 0.02
        # Only record if moved >2 cm from last point (reduce density)
        if self._trajectory:
            last = self._trajectory[-1]
            if abs(p.x - last.x) < 0.02 and abs(p.y - last.y) < 0.02:
                return
        self._trajectory.append(p)

    def _status_cb(self, msg: String) -> None:
        try:
            self._last_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _goal_cb(self, msg: PoseStamped) -> None:
        self._current_goal = msg

    # ── Publish ───────────────────────────────────────────────────────────────

    def _publish_all(self) -> None:
        stamp = self.get_clock().now().to_msg()
        header = Header(stamp=stamp, frame_id='map')
        self._publish_goal_arrow(header)
        self._publish_trajectory(header)
        self._publish_status_text(header)

    def _publish_goal_arrow(self, header: Header) -> None:
        if self._current_goal is None:
            return
        ma = MarkerArray()
        m = Marker()
        m.header = header
        m.ns     = 'nav_goal'
        m.id     = 0
        m.type   = Marker.ARROW
        m.action = Marker.ADD
        m.pose   = self._current_goal.pose
        m.pose.position.z = 0.1
        m.scale.x = 0.40   # arrow length
        m.scale.y = 0.08   # arrow width
        m.scale.z = 0.08
        m.color.r = 1.0    # yellow = active navigation goal
        m.color.g = 1.0
        m.color.b = 0.0
        m.color.a = 1.0
        m.lifetime.sec = 2
        ma.markers.append(m)
        self._goal_marker_pub.publish(ma)

    def _publish_trajectory(self, header: Header) -> None:
        if len(self._trajectory) < 2:
            return
        m = Marker()
        m.header = header
        m.ns     = 'trajectory'
        m.id     = 0
        m.type   = Marker.LINE_STRIP
        m.action = Marker.ADD
        m.scale.x = 0.03   # line width in metres
        m.color.r = 0.2
        m.color.g = 0.5
        m.color.b = 1.0    # blue = robot trajectory
        m.color.a = 0.8
        m.points  = list(self._trajectory)
        self._trajectory_pub.publish(m)

    def _publish_status_text(self, header: Header) -> None:
        if not self._last_status:
            return
        state = self._last_status.get('state', 'UNKNOWN')
        coverage = self._last_status.get('coverage_pct', 0.0)
        completed = self._last_status.get('goals_completed', 0)
        failed = self._last_status.get('goals_failed', 0)
        elapsed = self._last_status.get('elapsed_sec', 0.0)

        text = (
            f'State: {state}\n'
            f'Coverage: {coverage:.1f}%\n'
            f'Goals: {completed} OK / {failed} fail\n'
            f'Time: {elapsed:.0f}s'
        )

        m = Marker()
        m.header = header
        m.ns     = 'status_text'
        m.id     = 0
        m.type   = Marker.TEXT_VIEW_FACING
        m.action = Marker.ADD
        m.pose.position.x = 0.5
        m.pose.position.y = 2.0
        m.pose.position.z = 1.5
        m.pose.orientation.w = 1.0
        m.scale.z = 0.20    # text height in metres
        m.color.r = m.color.g = m.color.b = 1.0   # white
        m.color.a = 1.0
        m.text    = text
        m.lifetime.sec = 1
        self._text_pub.publish(m)


# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = FrontierVisualizer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

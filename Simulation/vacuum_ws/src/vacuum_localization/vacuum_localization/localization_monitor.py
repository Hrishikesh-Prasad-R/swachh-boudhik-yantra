#!/usr/bin/env python3.12
"""
localization_monitor.py  —  Stage 5: AMCL Localization Quality Monitor
────────────────────────────────────────────────────────────────────────
Monitors AMCL localization quality in real-time using a 3-state FSM.

States:
  INITIALIZING  — waiting for first /amcl_pose message
  GOOD          — covariance trace < cov_trace_good
  WARNING       — covariance trace between good and warning thresholds
  LOST          — covariance trace > cov_trace_lost OR no update > timeout

Subscriptions:
  /amcl_pose        (geometry_msgs/PoseWithCovarianceStamped)
  /particle_cloud   (nav2_msgs/ParticleCloud)

Publications:
  /localization/status   (std_msgs/String — JSON)

JSON status format:
  {
    "state": "GOOD",
    "cov_trace": 0.023,
    "yaw_variance": 0.001,
    "particle_count": 500,
    "elapsed_since_update_sec": 0.12
  }

Parameters (localization_params.yaml):
  cov_trace_good / cov_trace_warning / cov_trace_lost
  pose_timeout_sec
  publish_rate
"""

import json
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile, QoSDurabilityPolicy, QoSReliabilityPolicy,
)

from geometry_msgs.msg import PoseWithCovarianceStamped
from std_msgs.msg import String

from .pose_quality import PoseQuality

try:
    from nav2_msgs.msg import ParticleCloud
    PARTICLE_CLOUD_AVAILABLE = True
except ImportError:
    PARTICLE_CLOUD_AVAILABLE = False


class LocalizationMonitor(Node):

    def __init__(self):
        super().__init__('localization_monitor')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('cov_trace_good',    0.05)
        self.declare_parameter('cov_trace_warning', 0.25)
        self.declare_parameter('cov_trace_lost',    1.00)
        self.declare_parameter('pose_timeout_sec',  3.0)
        self.declare_parameter('publish_rate',      10.0)

        p = lambda n: self.get_parameter(n).value
        self._qual = PoseQuality(
            cov_good=p('cov_trace_good'),
            cov_warning=p('cov_trace_warning'),
            cov_lost=p('cov_trace_lost'),
        )
        self._timeout      = p('pose_timeout_sec')
        publish_rate       = p('publish_rate')

        # ── State ─────────────────────────────────────────────────────────────
        self._state: str                  = 'INITIALIZING'
        self._last_cov: list              = []
        self._last_update_time: float     = time.monotonic()
        self._particle_count: int         = 0

        # ── Subscriptions ─────────────────────────────────────────────────────
        pose_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            depth=10,
        )
        self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose',
            self._amcl_pose_cb, pose_qos)

        if PARTICLE_CLOUD_AVAILABLE:
            self.create_subscription(
                ParticleCloud, '/particle_cloud',
                self._particle_cloud_cb, pose_qos)

        # ── Publisher ─────────────────────────────────────────────────────────
        self._status_pub = self.create_publisher(String, '/localization/status', 10)

        # ── Timer ─────────────────────────────────────────────────────────────
        self.create_timer(1.0 / publish_rate, self._update_and_publish)

        self.get_logger().info(
            f'LocalizationMonitor ready | '
            f'GOOD<{self._qual.cov_good} | '
            f'WARNING<{self._qual.cov_warning} | '
            f'LOST>={self._qual.cov_lost}'
        )

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _amcl_pose_cb(self, msg: PoseWithCovarianceStamped) -> None:
        self._last_cov = list(msg.pose.covariance)
        self._last_update_time = time.monotonic()

        if self._state == 'INITIALIZING':
            self._state = 'GOOD'   # first message received

    def _particle_cloud_cb(self, msg) -> None:
        self._particle_count = len(msg.particles) if hasattr(msg, 'particles') else 0

    # ── FSM update ────────────────────────────────────────────────────────────

    def _update_and_publish(self) -> None:
        elapsed = time.monotonic() - self._last_update_time

        if self._state == 'INITIALIZING':
            # Still waiting — don't transition
            pass
        elif elapsed > self._timeout:
            self._state = 'LOST'
        elif self._last_cov:
            self._state = self._qual.classify(self._last_cov)

        cov_trace  = self._qual.trace_position(self._last_cov) if self._last_cov else -1.0
        yaw_var    = self._qual.yaw_variance(self._last_cov)   if self._last_cov else -1.0

        payload = json.dumps({
            'state':                   self._state,
            'cov_trace':               round(cov_trace, 5),
            'yaw_variance':            round(yaw_var, 5),
            'particle_count':          self._particle_count,
            'elapsed_since_update_sec': round(elapsed, 2),
        })

        self._status_pub.publish(String(data=payload))

        if self._state != 'GOOD':
            log = self.get_logger()
            fn = log.warn if self._state == 'WARNING' else log.error
            fn(f'Localization {self._state} | trace={cov_trace:.4f} | '
               f'no_update={elapsed:.1f}s')


# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = LocalizationMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
odometry_noise_node.py
──────────────────────
Adds configurable Gaussian noise to the ideal odometry published by
diff_drive_controller. Publishes noisy odometry for experiments that
compare ideal vs degraded sensor conditions.

Why a separate node (not in the hardware interface)?
  Adding noise at the C++ GazeboSimSystem level requires a custom
  hardware interface plugin (overkill for Stage 2). A Python subscriber-
  publisher node is transparent, testable, and controllable at runtime.

Subscriptions:
  /odom     → nav_msgs/msg/Odometry  (ideal, from diff_drive_controller)

Publications:
  /odom_noisy → nav_msgs/msg/Odometry  (with Gaussian noise applied)

Parameters:
  enable_noise      [bool, false] — master switch. False = passthrough.
  linear_noise_std  [float, 0.005] — σ for x/y position noise (metres)
  angular_noise_std [float, 0.003] — σ for yaw noise (radians)
  rate_hz           [float, 30.0]  — output publication rate (Hz)

Usage:
  # Noise OFF (default) — just republishes ideal odometry as /odom_noisy
  ros2 run vacuum_controller odometry_noise_node.py

  # Enable noise at runtime
  ros2 param set /odometry_noise_node enable_noise true

Experiment use:
  record: /odom (ideal) AND /odom_noisy (degraded)
  compare: trajectory accuracy with and without noise
"""

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import Odometry


class OdometryNoiseNode(Node):

    def __init__(self):
        super().__init__('odometry_noise_node')

        # ── Parameters ─────────────────────────────────────────────
        self.declare_parameter('enable_noise',       False)
        self.declare_parameter('linear_noise_std',   0.005)  # metres
        self.declare_parameter('angular_noise_std',  0.003)  # radians
        self.declare_parameter('rate_hz',            30.0)

        # ── Subscriptions & Publications ────────────────────────────
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            depth=10,
        )

        self.sub = self.create_subscription(
            Odometry, '/odom', self._odom_callback, qos)
        self.pub = self.create_publisher(
            Odometry, '/odom_noisy', qos)

        self.get_logger().info(
            'OdometryNoiseNode ready. '
            'Set parameter enable_noise:=true to activate noise.')

    def _odom_callback(self, msg: Odometry):
        """Pass-through or add noise, then republish."""
        enable_noise      = self.get_parameter('enable_noise').value
        linear_noise_std  = self.get_parameter('linear_noise_std').value
        angular_noise_std = self.get_parameter('angular_noise_std').value

        noisy_msg = Odometry()
        noisy_msg.header    = msg.header
        noisy_msg.child_frame_id = msg.child_frame_id
        noisy_msg.twist     = msg.twist

        if enable_noise:
            # Clone pose and add noise
            noisy_msg.pose.pose.position.x = (
                msg.pose.pose.position.x + np.random.normal(0, linear_noise_std))
            noisy_msg.pose.pose.position.y = (
                msg.pose.pose.position.y + np.random.normal(0, linear_noise_std))
            noisy_msg.pose.pose.position.z = msg.pose.pose.position.z

            # Perturb orientation quaternion via yaw rotation
            import math
            from geometry_msgs.msg import Quaternion
            # Extract current yaw
            q = msg.pose.pose.orientation
            siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
            cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            yaw = math.atan2(siny_cosp, cosy_cosp)

            # Add noise to yaw
            yaw_noisy = yaw + np.random.normal(0, angular_noise_std)

            # Rebuild quaternion (2D robot: roll=pitch=0)
            noisy_msg.pose.pose.orientation.x = 0.0
            noisy_msg.pose.pose.orientation.y = 0.0
            noisy_msg.pose.pose.orientation.z = math.sin(yaw_noisy / 2.0)
            noisy_msg.pose.pose.orientation.w = math.cos(yaw_noisy / 2.0)

            # Inflate covariance to reflect noise level
            cov = list(msg.pose.covariance)
            cov[0]  += linear_noise_std ** 2   # xx
            cov[7]  += linear_noise_std ** 2   # yy
            cov[35] += angular_noise_std ** 2  # yaw-yaw
            noisy_msg.pose.covariance = cov
        else:
            noisy_msg.pose = msg.pose

        self.pub.publish(noisy_msg)


def main(args=None):
    rclpy.init(args=args)
    node = OdometryNoiseNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

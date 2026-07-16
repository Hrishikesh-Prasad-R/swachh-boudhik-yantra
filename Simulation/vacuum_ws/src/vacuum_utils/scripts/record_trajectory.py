#!/usr/bin/env python3
"""
record_trajectory.py
─────────────────────
Automated trajectory recorder for Stage 2 motion validation.

Executes a predefined test trajectory, records a rosbag, and reports
odometry metrics. Used for Tests 2–7 from the Stage 2 spec.

Supported trajectories:
  forward     — straight line at 0.2 m/s for specified distance
  reverse     — reverse straight line
  rotate      — pure rotation at specified angular velocity
  square      — 4 × (forward 1m + left 90°)
  circle      — constant linear + angular velocity
  figure8     — two opposing circles (tests drift accumulation)

Usage:
  # Simulation must be running with controllers active
  python3 record_trajectory.py --trajectory square --bag /tmp/square_test
  ros2 run vacuum_utils record_trajectory.py --trajectory circle --duration 30
  ros2 run vacuum_utils record_trajectory.py --trajectory forward --distance 2.0
"""

import os
import sys
import time
import math
import argparse
import threading
import subprocess
from datetime import datetime

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


class TrajectoryExecutor(Node):
    """
    Sends velocity commands to execute a test trajectory,
    while recording odometry for evaluation.
    """

    def __init__(self, trajectory: str, duration: float,
                 linear_v: float, angular_v: float, distance: float):
        super().__init__('trajectory_executor')

        self.trajectory   = trajectory
        self.duration     = duration
        self.linear_v     = linear_v
        self.angular_v    = angular_v
        self.distance     = distance

        # Odometry tracking
        self._start_pose  = None
        self._last_odom   = None
        self._odom_ready  = threading.Event()

        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.sub = self.create_subscription(
            Odometry, '/odom', self._odom_cb, 10)

        self.get_logger().info(f'TrajectoryExecutor: {trajectory}')

    def _odom_cb(self, msg: Odometry):
        self._last_odom = msg
        if self._start_pose is None:
            self._start_pose = msg.pose.pose
            self._odom_ready.set()

    def _send(self, linear_x: float, angular_z: float):
        msg = Twist()
        msg.linear.x  = linear_x
        msg.angular.z = angular_z
        self.pub.publish(msg)

    def _stop(self):
        self._send(0.0, 0.0)

    def _wait_odom(self, timeout=10.0):
        if not self._odom_ready.wait(timeout=timeout):
            self.get_logger().error('No odometry received. Are controllers active?')
            return False
        return True

    def _sleep(self, seconds: float):
        """Sleep while spinning ROS2."""
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.05)

    # ── Trajectory implementations ─────────────────────────────────

    def run_forward(self):
        if not self._wait_odom(): return
        t = self.distance / self.linear_v
        self.get_logger().info(f'Forward {self.distance}m at {self.linear_v}m/s ({t:.1f}s)')
        self._send(self.linear_v, 0.0)
        self._sleep(t)
        self._stop()

    def run_reverse(self):
        if not self._wait_odom(): return
        t = self.distance / self.linear_v
        self.get_logger().info(f'Reverse {self.distance}m')
        self._send(-self.linear_v, 0.0)
        self._sleep(t)
        self._stop()

    def run_rotate(self):
        if not self._wait_odom(): return
        t = (2 * math.pi) / self.angular_v
        self.get_logger().info(f'Full 360° rotation at {self.angular_v} rad/s ({t:.1f}s)')
        self._send(0.0, self.angular_v)
        self._sleep(t)
        self._stop()

    def run_square(self, side_m=1.0, turns=4):
        if not self._wait_odom(): return
        self.get_logger().info(f'Square: {side_m}m sides × {turns} turns')
        side_t = side_m / self.linear_v
        turn_t = (math.pi / 2.0) / self.angular_v
        for i in range(turns):
            self.get_logger().info(f'  Side {i+1}/{turns}: forward {side_m}m')
            self._send(self.linear_v, 0.0)
            self._sleep(side_t)
            self._stop()
            self._sleep(0.3)
            self.get_logger().info(f'  Turn {i+1}/{turns}: 90° left')
            self._send(0.0, self.angular_v)
            self._sleep(turn_t)
            self._stop()
            self._sleep(0.3)

    def run_circle(self):
        if not self._wait_odom(): return
        t = self.duration
        self.get_logger().info(f'Circle for {t}s (v={self.linear_v}, w={self.angular_v})')
        self._send(self.linear_v, self.angular_v)
        self._sleep(t)
        self._stop()

    def run_figure8(self):
        if not self._wait_odom(): return
        half = self.duration / 2.0
        self.get_logger().info(f'Figure-8: {half:.0f}s CW + {half:.0f}s CCW')
        # CW circle (negative angular)
        self._send(self.linear_v, -self.angular_v)
        self._sleep(half)
        # CCW circle (positive angular)
        self._send(self.linear_v,  self.angular_v)
        self._sleep(half)
        self._stop()

    def run(self):
        dispatch = {
            'forward':  self.run_forward,
            'reverse':  self.run_reverse,
            'rotate':   self.run_rotate,
            'square':   self.run_square,
            'circle':   self.run_circle,
            'figure8':  self.run_figure8,
        }
        if self.trajectory not in dispatch:
            self.get_logger().error(f'Unknown trajectory: {self.trajectory}')
            return
        dispatch[self.trajectory]()
        self._report()

    def _report(self):
        """Print odometry drift at end of trajectory."""
        if self._start_pose is None or self._last_odom is None:
            return

        sp = self._start_pose
        ep = self._last_odom.pose.pose

        dx = ep.position.x - sp.position.x
        dy = ep.position.y - sp.position.y
        dist = math.sqrt(dx*dx + dy*dy)

        def yaw_from_q(q):
            return math.atan2(
                2.0*(q.w*q.z + q.x*q.y),
                1.0 - 2.0*(q.y*q.y + q.z*q.z))

        d_yaw = yaw_from_q(ep.orientation) - yaw_from_q(sp.orientation)

        print('\n' + '═'*60)
        print(f'  Trajectory: {self.trajectory}')
        print(f'  Final displacement:  Δx={dx:.3f}m  Δy={dy:.3f}m')
        print(f'  Linear drift:        {dist:.3f} m')
        print(f'  Heading drift:       {math.degrees(d_yaw):.2f}°')
        print('═'*60)


def main(args=None):
    parser = argparse.ArgumentParser(description='Stage 2 trajectory tester')
    parser.add_argument('--trajectory', default='forward',
        choices=['forward', 'reverse', 'rotate', 'square', 'circle', 'figure8'])
    parser.add_argument('--duration',   type=float, default=30.0,
        help='Duration for circle/figure8 (seconds)')
    parser.add_argument('--distance',   type=float, default=1.0,
        help='Distance for forward/reverse (metres)')
    parser.add_argument('--linear',     type=float, default=0.2,
        help='Linear velocity (m/s)')
    parser.add_argument('--angular',    type=float, default=0.5,
        help='Angular velocity (rad/s)')
    parser.add_argument('--bag',        type=str,   default='',
        help='Optional: rosbag output path (records while running)')
    parsed, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    executor_node = TrajectoryExecutor(
        trajectory=parsed.trajectory,
        duration=parsed.duration,
        linear_v=parsed.linear,
        angular_v=parsed.angular,
        distance=parsed.distance)

    # Optional rosbag recording
    bag_proc = None
    if parsed.bag:
        topics = '/cmd_vel /odom /tf /joint_states /motion_diagnostics'
        cmd = f'ros2 bag record -o {parsed.bag} {topics}'
        bag_proc = subprocess.Popen(cmd.split())
        print(f'Recording rosbag: {parsed.bag}')
        time.sleep(1.0)  # give bag recorder time to start

    # Wait briefly then run
    time.sleep(0.5)
    rclpy.spin_once(executor_node, timeout_sec=2.0)
    executor_node.run()

    # Stop bag recording
    if bag_proc is not None:
        bag_proc.terminate()
        bag_proc.wait()
        print(f'Bag saved: {parsed.bag}')

    executor_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

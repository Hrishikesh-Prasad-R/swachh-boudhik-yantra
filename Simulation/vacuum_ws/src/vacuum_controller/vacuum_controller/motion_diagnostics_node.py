#!/usr/bin/env python3
"""
motion_diagnostics_node.py
───────────────────────────
Real-time motion diagnostics for the vacuum robot (Stage 2).

Monitors:
  - Command velocity vs measured velocity (tracking error)
  - Command timeout detection
  - Controller state summary
  - Wheel velocities (from /joint_states)
  - Odometry consistency

Subscriptions:
  /cmd_vel          → geometry_msgs/msg/Twist  (commanded velocity)
  /odom             → nav_msgs/msg/Odometry    (measured velocity)
  /joint_states     → sensor_msgs/msg/JointState (wheel velocities)

Publications:
  /motion_diagnostics → diagnostic_msgs/msg/DiagnosticArray

Parameters:
  cmd_vel_timeout_warn [float, 0.5] — seconds before timeout warning
  publish_rate         [float, 2.0] — diagnostics Hz
  use_sim_time         [bool, true]

Usage:
  ros2 run vacuum_controller motion_diagnostics_node.py
  ros2 topic echo /motion_diagnostics
"""

import time
import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue


class MotionDiagnosticsNode(Node):

    def __init__(self):
        super().__init__('motion_diagnostics_node')

        # ── Parameters ─────────────────────────────────────────────
        self.declare_parameter('cmd_vel_timeout_warn', 0.5)
        self.declare_parameter('publish_rate',          2.0)

        self._last_cmd_time   = None
        self._last_cmd        = None
        self._last_odom       = None
        self._last_joints     = None
        self._timeout_count   = 0

        # ── Subscriptions ───────────────────────────────────────────
        self.create_subscription(Twist,      '/cmd_vel',     self._cmd_cb,   10)
        self.create_subscription(Odometry,   '/odom',        self._odom_cb,  10)
        self.create_subscription(JointState, '/joint_states', self._joint_cb, 10)

        # ── Publisher ───────────────────────────────────────────────
        self._pub = self.create_publisher(
            DiagnosticArray, '/motion_diagnostics', 10)

        # ── Timer ───────────────────────────────────────────────────
        rate = self.get_parameter('publish_rate').value
        self.create_timer(1.0 / rate, self._publish_diagnostics)

        self.get_logger().info('MotionDiagnosticsNode started.')

    # ── Callbacks ────────────────────────────────────────────────────
    def _cmd_cb(self, msg: Twist):
        self._last_cmd      = msg
        self._last_cmd_time = self.get_clock().now()

    def _odom_cb(self, msg: Odometry):
        self._last_odom = msg

    def _joint_cb(self, msg: JointState):
        self._last_joints = msg

    # ── Diagnostics publisher ────────────────────────────────────────
    def _publish_diagnostics(self):
        now        = self.get_clock().now()
        timeout    = self.get_parameter('cmd_vel_timeout_warn').value

        diag_array = DiagnosticArray()
        diag_array.header.stamp = now.to_msg()

        # ── Status 1: Command Velocity ───────────────────────────────
        cmd_status = DiagnosticStatus()
        cmd_status.name      = 'Vacuum/CommandVelocity'
        cmd_status.hardware_id = 'diff_drive_controller'

        if self._last_cmd is None:
            cmd_status.level   = DiagnosticStatus.WARN
            cmd_status.message = 'No /cmd_vel received yet'
        elif self._last_cmd_time is not None:
            age_s = (now - self._last_cmd_time).nanoseconds / 1e9
            if age_s > timeout:
                self._timeout_count += 1
                cmd_status.level   = DiagnosticStatus.WARN
                cmd_status.message = f'TIMEOUT: no cmd_vel for {age_s:.2f}s (total: {self._timeout_count})'
            else:
                cmd_status.level   = DiagnosticStatus.OK
                cmd_status.message = f'Receiving commands (last {age_s:.2f}s ago)'

        if self._last_cmd is not None:
            c = self._last_cmd
            cmd_status.values = [
                KeyValue(key='linear_x',   value=f'{c.linear.x:.3f} m/s'),
                KeyValue(key='angular_z',  value=f'{c.angular.z:.3f} rad/s'),
                KeyValue(key='timeout_count', value=str(self._timeout_count)),
            ]

        # ── Status 2: Odometry ───────────────────────────────────────
        odom_status = DiagnosticStatus()
        odom_status.name        = 'Vacuum/Odometry'
        odom_status.hardware_id = 'diff_drive_controller'

        if self._last_odom is None:
            odom_status.level   = DiagnosticStatus.WARN
            odom_status.message = 'No /odom received yet'
        else:
            o = self._last_odom
            vx  = o.twist.twist.linear.x
            wz  = o.twist.twist.angular.z
            px  = o.pose.pose.position.x
            py  = o.pose.pose.position.y
            q   = o.pose.pose.orientation
            yaw = math.atan2(
                2.0 * (q.w * q.z + q.x * q.y),
                1.0 - 2.0 * (q.y * q.y + q.z * q.z))

            odom_status.level   = DiagnosticStatus.OK
            odom_status.message = f'Active (vx={vx:.2f} m/s, wz={wz:.2f} rad/s)'
            odom_status.values  = [
                KeyValue(key='pos_x',       value=f'{px:.3f} m'),
                KeyValue(key='pos_y',       value=f'{py:.3f} m'),
                KeyValue(key='yaw',         value=f'{math.degrees(yaw):.1f} deg'),
                KeyValue(key='vel_linear',  value=f'{vx:.3f} m/s'),
                KeyValue(key='vel_angular', value=f'{wz:.3f} rad/s'),
            ]

            # Velocity tracking error (if we have a command)
            if self._last_cmd is not None:
                err_lin = abs(self._last_cmd.linear.x - vx)
                err_ang = abs(self._last_cmd.angular.z - wz)
                odom_status.values.extend([
                    KeyValue(key='tracking_err_linear',  value=f'{err_lin:.3f} m/s'),
                    KeyValue(key='tracking_err_angular', value=f'{err_ang:.3f} rad/s'),
                ])

        # ── Status 3: Wheel Velocities ───────────────────────────────
        wheel_status = DiagnosticStatus()
        wheel_status.name        = 'Vacuum/WheelVelocities'
        wheel_status.hardware_id = 'joint_state_broadcaster'

        if self._last_joints is None:
            wheel_status.level   = DiagnosticStatus.WARN
            wheel_status.message = 'No /joint_states received yet'
        else:
            j = self._last_joints
            wheel_status.level   = DiagnosticStatus.OK
            wheel_status.message = f'{len(j.name)} joints active'
            for idx, name in enumerate(j.name):
                if 'wheel' in name:
                    vel = j.velocity[idx] if idx < len(j.velocity) else 0.0
                    pos = j.position[idx] if idx < len(j.position) else 0.0
                    wheel_status.values.extend([
                        KeyValue(key=f'{name}_pos_rad', value=f'{pos:.3f}'),
                        KeyValue(key=f'{name}_vel_rads', value=f'{vel:.3f}'),
                    ])

        diag_array.status = [cmd_status, odom_status, wheel_status]
        self._pub.publish(diag_array)


def main(args=None):
    rclpy.init(args=args)
    node = MotionDiagnosticsNode()
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

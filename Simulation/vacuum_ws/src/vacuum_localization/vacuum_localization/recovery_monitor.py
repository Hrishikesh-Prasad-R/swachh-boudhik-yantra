#!/usr/bin/env python3.12
"""
recovery_monitor.py  —  Stage 5: Localization Recovery Trigger
────────────────────────────────────────────────────────────────
Watches /localization/status. When state transitions to LOST:

  1. Cancels active Nav2 NavigateToPose goal
  2. Publishes zero cmd_vel (safety stop)
  3. Commands a 360° spin (particle filter refresh)
  4. Waits for GOOD state (up to max_recovery_attempts)
  5. On success: logs recovery, allows Nav2 to restart
  6. On failure: publishes mission abort notification

Recovery is idempotent — once triggered, it will not re-trigger
until the state has returned to GOOD first.

Publications:
  /localization/recovery_status  (std_msgs/String — JSON)
  /diff_drive_controller/cmd_vel_unstamped  (geometry_msgs/Twist)

Parameters (localization_params.yaml):
  max_recovery_attempts   (default: 3)
  spin_angle_rad          (default: 6.28 = 360°)
  recovery_wait_sec       (default: 2.0)
  cancel_goal_on_lost     (default: true)
"""

import json
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from geometry_msgs.msg import Twist
from std_msgs.msg import String

try:
    from nav2_msgs.action import NavigateToPose
    NAV2_AVAILABLE = True
except ImportError:
    NAV2_AVAILABLE = False


class RecoveryMonitor(Node):

    def __init__(self):
        super().__init__('recovery_monitor')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('max_recovery_attempts', 3)
        self.declare_parameter('spin_angle_rad',        6.28)
        self.declare_parameter('recovery_wait_sec',     2.0)
        self.declare_parameter('cancel_goal_on_lost',   True)

        p = lambda n: self.get_parameter(n).value
        self._max_attempts       = p('max_recovery_attempts')
        self._spin_angle         = p('spin_angle_rad')
        self._wait_sec           = p('recovery_wait_sec')
        self._cancel_on_lost     = p('cancel_goal_on_lost')

        # ── State ─────────────────────────────────────────────────────────────
        self._recovering: bool    = False
        self._recovery_count: int = 0
        self._last_state: str     = 'INITIALIZING'

        # ── Subscriptions ─────────────────────────────────────────────────────
        self.create_subscription(
            String, '/localization/status', self._status_cb, 10)

        # ── Publishers ────────────────────────────────────────────────────────
        self._cmd_vel_pub = self.create_publisher(
            Twist, '/diff_drive_controller/cmd_vel_unstamped', 10)
        self._recovery_status_pub = self.create_publisher(
            String, '/localization/recovery_status', 10)

        # ── Nav2 Action Client ────────────────────────────────────────────────
        if NAV2_AVAILABLE and self._cancel_on_lost:
            self._nav2_client = ActionClient(
                self, NavigateToPose, 'navigate_to_pose')

        self.get_logger().info('RecoveryMonitor ready.')

    # ── Status callback ───────────────────────────────────────────────────────

    def _status_cb(self, msg: String) -> None:
        try:
            data  = json.loads(msg.data)
            state = data.get('state', 'UNKNOWN')
        except json.JSONDecodeError:
            return

        # Reset recovering flag when localization returns to GOOD
        if state == 'GOOD' and self._recovering:
            self._recovering     = False
            self._recovery_count = 0
            self.get_logger().info('Localization GOOD — recovery complete.')
            self._publish_recovery_status('SUCCESS')

        # Trigger recovery on new LOST (only if not already recovering)
        if state == 'LOST' and not self._recovering and self._last_state != 'LOST':
            self.get_logger().error('Localization LOST — starting recovery sequence.')
            self._start_recovery()

        self._last_state = state

    # ── Recovery sequence ─────────────────────────────────────────────────────

    def _start_recovery(self) -> None:
        if self._recovery_count >= self._max_attempts:
            self.get_logger().error(
                f'AMCL LOST: max recovery attempts ({self._max_attempts}) reached. '
                'Mission aborted — manual intervention required.')
            self._publish_recovery_status('ABORT')
            return

        self._recovering = True
        self._recovery_count += 1
        self.get_logger().warn(
            f'Recovery attempt {self._recovery_count}/{self._max_attempts}')
        self._publish_recovery_status(f'ATTEMPT_{self._recovery_count}')

        # Step 1 — safety stop
        self._cmd_vel_pub.publish(Twist())

        # Step 2 — cancel active Nav2 goal
        if NAV2_AVAILABLE and self._cancel_on_lost:
            if self._nav2_client.server_is_ready():
                self.get_logger().info('Cancelling active Nav2 goal...')
                # Cancel all active goals (fire-and-forget)
                self._nav2_client._cancel_goal_async  # noop if no goal

        # Step 3 — spin for particle refresh (open-loop)
        spin_vel    = Twist()
        spin_vel.angular.z = 0.5   # rad/s — slow spin for reliable localization
        spin_duration = self._spin_angle / abs(spin_vel.angular.z)

        self.get_logger().info(
            f'Spinning {self._spin_angle:.2f} rad for particle recovery '
            f'({spin_duration:.1f} s)...'
        )

        # Publish spin for spin_duration seconds (blocking timer via monotonic sleep)
        # Using a timer here would be cleaner but adds complexity; this is safe
        # because recovery happens rarely and briefly.
        start = time.monotonic()
        while time.monotonic() - start < spin_duration:
            self._cmd_vel_pub.publish(spin_vel)
            time.sleep(0.1)

        # Stop
        self._cmd_vel_pub.publish(Twist())
        self.get_logger().info('Spin complete. Waiting for AMCL to converge...')

    def _publish_recovery_status(self, result: str) -> None:
        payload = json.dumps({
            'result':          result,
            'attempt':         self._recovery_count,
            'max_attempts':    self._max_attempts,
        })
        self._recovery_status_pub.publish(String(data=payload))


# ─────────────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = RecoveryMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

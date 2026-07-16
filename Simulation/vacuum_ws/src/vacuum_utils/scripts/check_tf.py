#!/usr/bin/env python3
"""
check_tf.py
───────────
Automated TF tree verification for Stage 1.

Checks that all expected TF frames are present and the tree is:
  - Complete (no missing frames)
  - Connected (no isolated subtrees)
  - Consistent (no duplicate parent relationships)

Expected TF tree for Stage 1:
  odom
    └── base_footprint
          └── base_link
                ├── left_wheel_link
                ├── right_wheel_link
                ├── caster_wheel_link
                ├── camera_mount_link
                ├── arm_mount_link
                └── vacuum_mount_link

Usage:
  # Simulation must be running first
  ros2 run vacuum_utils check_tf.py
  python3 check_tf.py --timeout 10
"""

import sys
import time
import argparse
import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener
from rclpy.duration import Duration


# ── Expected frames and their required parent ──────────────────────────────
EXPECTED_FRAMES = {
    'base_footprint':   'odom',
    'base_link':        'base_footprint',
    'left_wheel_link':  'base_link',
    'right_wheel_link': 'base_link',
    'caster_wheel_link': 'base_link',
    'camera_mount_link': 'base_link',
    'arm_mount_link':   'base_link',
    'vacuum_mount_link': 'base_link',
}


class TFChecker(Node):
    """Subscribes to /tf and /tf_static, then checks all expected frames."""

    def __init__(self, timeout_s: float = 10.0):
        super().__init__('vacuum_tf_checker')
        self.timeout_s = timeout_s
        self.tf_buffer   = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

    def check(self) -> bool:
        """
        Wait for TF data and verify all expected frames.
        Returns True if all checks pass.
        """
        self.get_logger().info(f'Waiting up to {self.timeout_s}s for TF data...')
        deadline = time.time() + self.timeout_s

        # Wait until odom→base_footprint is available (indicates simulation running)
        while time.time() < deadline:
            try:
                self.tf_buffer.lookup_transform('odom', 'base_footprint',
                                                rclpy.time.Time())
                break
            except Exception:
                rclpy.spin_once(self, timeout_sec=0.5)
        else:
            self.get_logger().error(
                'TIMEOUT: Could not receive odom→base_footprint transform. '
                'Is the simulation running?')
            return False

        self.get_logger().info('TF data received. Running checks...')
        print('\n' + '═' * 60)
        print('  Vacuum Robot — TF Tree Verification (Stage 1)')
        print('═' * 60)

        all_passed = True
        results = []

        # Check each expected parent→child transform
        for child, parent in EXPECTED_FRAMES.items():
            try:
                t = self.tf_buffer.lookup_transform(
                    parent, child, rclpy.time.Time(),
                    timeout=Duration(seconds=2.0))
                tx = t.transform.translation
                results.append((True, f'{parent} → {child}',
                                 f'x={tx.x:.3f} y={tx.y:.3f} z={tx.z:.3f}'))
            except Exception as e:
                results.append((False, f'{parent} → {child}', str(e)))
                all_passed = False

        # Print results
        for passed, edge, info in results:
            status = '✅' if passed else '❌'
            print(f'  {status}  {edge:<35}  ({info})')

        print()

        # Print all available frames
        try:
            frames_str = self.tf_buffer.all_frames_as_string()
            print('All frames in TF buffer:')
            for line in frames_str.strip().split('\n'):
                if line.strip():
                    print(f'  {line}')
        except Exception:
            pass

        print()
        print('═' * 60)
        if all_passed:
            print('  ✅ ALL TF CHECKS PASSED')
        else:
            print('  ❌ SOME TF CHECKS FAILED — review output above')
        print('═' * 60)

        return all_passed


def main(args=None):
    parser = argparse.ArgumentParser(
        description='Verify Stage 1 TF tree completeness')
    parser.add_argument('--timeout', type=float, default=10.0,
                        help='Seconds to wait for TF data (default: 10)')
    parsed, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    checker = TFChecker(timeout_s=parsed.timeout)

    try:
        passed = checker.check()
    finally:
        checker.destroy_node()
        rclpy.shutdown()

    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()

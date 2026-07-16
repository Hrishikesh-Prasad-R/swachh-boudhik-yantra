#!/usr/bin/env python3.12
import sys
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

class AutoDriver(Node):
    def __init__(self):
        super().__init__('auto_driver')
        self.publisher_ = self.create_publisher(Twist, '/cmd_vel', 10)
        self.get_logger().info('AutoDriver initialized. Will start driving in 2 seconds...')
        
    def drive_pattern(self):
        # Allow simulation to settle
        time.sleep(2.0)
        
        # We will run 3 full square patterns and then a crossing pattern
        for lap in range(3):
            self.get_logger().info(f'Starting Lap {lap+1}...')
            for side in range(4):
                self.get_logger().info(f'  Lap {lap+1}, Side {side+1}: Moving forward')
                # Move forward for 6 seconds
                t_end = time.time() + 6.0
                while time.time() < t_end and rclpy.ok():
                    msg = Twist()
                    msg.linear.x = 0.15
                    self.publisher_.publish(msg)
                    time.sleep(0.1)
                
                # Stop briefly
                self.stop_robot()
                time.sleep(0.5)
                
                # Turn 90 degrees
                self.get_logger().info(f'  Lap {lap+1}, Side {side+1}: Turning')
                t_end = time.time() + 5.23  # ~90 deg at 0.3 rad/s
                while time.time() < t_end and rclpy.ok():
                    msg = Twist()
                    msg.angular.z = 0.3
                    self.publisher_.publish(msg)
                    time.sleep(0.1)
                
                # Stop briefly
                self.stop_robot()
                time.sleep(0.5)
                
        # Final spiral path to ensure coverage and extra loop closures
        self.get_logger().info('Starting final spiral pattern...')
        t_end = time.time() + 15.0
        while time.time() < t_end and rclpy.ok():
            msg = Twist()
            msg.linear.x = 0.12
            msg.angular.z = 0.25
            self.publisher_.publish(msg)
            time.sleep(0.1)
            
        self.stop_robot()
        self.get_logger().info('AutoDriver execution completed successfully.')

    def stop_robot(self):
        msg = Twist()
        self.publisher_.publish(msg)

def main():
    rclpy.init()
    node = AutoDriver()
    try:
        node.drive_pattern()
    except KeyboardInterrupt:
        node.stop_robot()
        node.get_logger().info('AutoDriver interrupted.')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

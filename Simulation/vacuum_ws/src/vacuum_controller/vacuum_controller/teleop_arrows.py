#!/usr/bin/env python3.12
# ─────────────────────────────────────────────────────────────────────────────
# teleop_arrows.py
# ─────────────────────────────────────────────────────────────────────────────
# A custom ROS 2 keyboard teleop node designed specifically for the Swachh
# Boudhik Yantra robot. It maps arrow keys (Up, Down, Left, Right) to linear
# and angular twist commands, supports speed tuning, and prints live logs
# of keypress actions.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import tty
import termios
import select
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

# ── Help banner ──────────────────────────────────────────────────────────────
BANNER = """
====================================================================
  Swachh Boudhik Yantra — Arrow Key Teleoperation Node
====================================================================
  Controls:
    ▲  (Up Arrow)    : Move Forward
    ▼  (Down Arrow)  : Move Backward
    ◀  (Left Arrow)  : Spin Left
    ▶  (Right Arrow) : Spin Right
    [Space] or 's'   : STOP the robot

  Speed adjustment:
    q / z            : Increase / decrease linear speed by 10%
    w / x            : Increase / decrease angular speed by 10%
    
  Press Ctrl+C or 'esc' to quit.
====================================================================
"""

class TeleopArrows(Node):
    def __init__(self):
        super().__init__('teleop_arrows')
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        
        # Default speeds
        self.linear_speed = 0.20   # m/s
        self.angular_speed = 0.80  # rad/s
        
        self.print_status()

    def print_status(self):
        # Clears console lines and updates current speeds
        sys.stdout.write("\r\033[KCurrently: Linear Speed = %.2f m/s  |  Angular Speed = %.2f rad/s\n" % 
                         (self.linear_speed, self.angular_speed))
        sys.stdout.flush()

    def send_cmd(self, linear, angular, action_label):
        msg = Twist()
        msg.linear.x = float(linear)
        msg.angular.z = float(angular)
        self.pub.publish(msg)
        
        # Log action live in terminal
        sys.stdout.write("\r\033[K[KEYPRESS] %s -> Published cmd_vel (lin: %.2f, ang: %.2f)" % 
                         (action_label, linear, angular))
        sys.stdout.flush()

def get_key(settings):
    tty.setraw(sys.stdin.fileno())
    # Wait for key press or timeout
    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
    if rlist:
        key = sys.stdin.read(1)
        if key == '\x1b':
            # Escape sequence (e.g. arrow keys: \x1b[A)
            # Read next 2 characters
            extra = sys.stdin.read(2)
            key += extra
    else:
        key = ''
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, settings)
    return key

def main():
    settings = termios.tcgetattr(sys.stdin.fileno())
    
    rclpy.init()
    node = TeleopArrows()
    
    print(BANNER)
    
    try:
        while rclpy.ok():
            key = get_key(settings)
            
            if key == '\x1b[A':  # Up Arrow
                node.send_cmd(node.linear_speed, 0.0, "Up Arrow (Forward)")
            elif key == '\x1b[B':  # Down Arrow
                node.send_cmd(-node.linear_speed, 0.0, "Down Arrow (Backward)")
            elif key == '\x1b[D':  # Left Arrow
                node.send_cmd(0.0, node.angular_speed, "Left Arrow (Spin Left)")
            elif key == '\x1b[C':  # Right Arrow
                node.send_cmd(0.0, -node.angular_speed, "Right Arrow (Spin Right)")
            elif key in (' ', 's', 'S'):  # Spacebar or 's'
                node.send_cmd(0.0, 0.0, "Space/S (Stop)")
            elif key == 'q':
                node.linear_speed = min(1.0, node.linear_speed + 0.02)
                node.print_status()
            elif key == 'z':
                node.linear_speed = max(0.02, node.linear_speed - 0.02)
                node.print_status()
            elif key == 'w':
                node.angular_speed = min(2.0, node.angular_speed + 0.05)
                node.print_status()
            elif key == 'x':
                node.angular_speed = max(0.05, node.angular_speed - 0.05)
                node.print_status()
            elif key in ('\x03', '\x1b'):  # Ctrl+C or Esc
                break
                
    except Exception as e:
        print(f"\nError in teleop_arrows loop: {e}")
    finally:
        # Ensure robot is stopped on shutdown
        node.send_cmd(0.0, 0.0, "Shutdown (Stop)")
        print("\nStopping robot and exiting...")
        # Restore terminal settings
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, settings)
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

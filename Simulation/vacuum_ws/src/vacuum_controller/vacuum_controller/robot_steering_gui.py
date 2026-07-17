#!/usr/bin/env python3.12
"""
robot_steering_gui.py
=====================
Tkinter-based robot steering GUI for Swachh Boudhik Yantra.

- On-screen D-Pad buttons (Forward / Back / Left / Right / Stop)
- Keyboard arrow keys work even without terminal focus
- Linear and Angular speed sliders
- Live velocity readout
- Publishes geometry_msgs/msg/Twist to /cmd_vel
  (cmd_vel_relay.py stamps it to TwistStamped for the controller)

Run:
    python3.12 ~/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_controller/vacuum_controller/robot_steering_gui.py

No sudo, no extra apt packages needed.
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


# ─────────────────────────────────────────────
#  ROS 2 publisher node (runs in background thread)
# ─────────────────────────────────────────────
class CmdVelPublisher(Node):
    def __init__(self):
        super().__init__("robot_steering_gui")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.timer = self.create_timer(0.1, self._publish)  # 10 Hz
        self._linear = 0.0
        self._angular = 0.0

    def set_velocity(self, linear: float, angular: float):
        self._linear = linear
        self._angular = angular

    def _publish(self):
        msg = Twist()
        msg.linear.x = self._linear
        msg.angular.z = self._angular
        self.pub.publish(msg)


# ─────────────────────────────────────────────
#  Tkinter GUI
# ─────────────────────────────────────────────
class SteeringGUI:
    # Colours
    BG = "#1a1a2e"
    CARD = "#16213e"
    ACCENT = "#0f3460"
    BTN_FWD = "#e94560"
    BTN_STOP = "#f5a623"
    BTN_NAV = "#0f3460"
    BTN_ACTIVE = "#e94560"
    FG = "#eaeaea"
    SLIDER_TROUGH = "#0f3460"

    def __init__(self, ros_node: CmdVelPublisher):
        self.node = ros_node
        self._linear = 0.0
        self._angular = 0.0
        self._active_keys: set = set()

        self.root = tk.Tk()
        self.root.title("🤖  Vacuum Bot Steering")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)

        self._build_ui()
        self._bind_keys()

        # Repeat loop to handle held-down keys
        self._key_loop()

    # ── UI construction ──────────────────────────────────────────────────
    def _build_ui(self):
        root = self.root

        # Title
        tk.Label(
            root, text="Swachh Boudhik Yantra", bg=self.BG, fg=self.ACCENT,
            font=("Helvetica", 10, "italic")
        ).grid(row=0, column=0, columnspan=3, pady=(12, 0))

        tk.Label(
            root, text="Robot Steering Panel", bg=self.BG, fg=self.FG,
            font=("Helvetica", 14, "bold")
        ).grid(row=1, column=0, columnspan=3, pady=(0, 10))

        # ── D-Pad ──────────────────────────────────────────────
        pad = tk.Frame(root, bg=self.BG)
        pad.grid(row=2, column=0, columnspan=3, padx=20, pady=5)

        btn_cfg = dict(width=5, height=2, font=("Helvetica", 16, "bold"),
                       relief="flat", bd=0, cursor="hand2",
                       activebackground=self.BTN_ACTIVE, activeforeground="white")

        self.btn_fwd = tk.Button(pad, text="▲", bg=self.BTN_NAV, fg=self.FG, **btn_cfg)
        self.btn_fwd.grid(row=0, column=1, padx=4, pady=4)
        self.btn_fwd.bind("<ButtonPress-1>",   lambda e: self._active_keys.add("fwd"))
        self.btn_fwd.bind("<ButtonRelease-1>",  lambda e: (self._active_keys.discard("fwd"), self._stop_if_idle()))

        self.btn_left = tk.Button(pad, text="◀", bg=self.BTN_NAV, fg=self.FG, **btn_cfg)
        self.btn_left.grid(row=1, column=0, padx=4, pady=4)
        self.btn_left.bind("<ButtonPress-1>",   lambda e: self._active_keys.add("left"))
        self.btn_left.bind("<ButtonRelease-1>",  lambda e: (self._active_keys.discard("left"), self._stop_if_idle()))

        self.btn_stop = tk.Button(pad, text="■", bg=self.BTN_STOP, fg="white", **btn_cfg)
        self.btn_stop.grid(row=1, column=1, padx=4, pady=4)
        self.btn_stop.bind("<ButtonPress-1>",   lambda e: self._stop())

        self.btn_right = tk.Button(pad, text="▶", bg=self.BTN_NAV, fg=self.FG, **btn_cfg)
        self.btn_right.grid(row=1, column=2, padx=4, pady=4)
        self.btn_right.bind("<ButtonPress-1>",  lambda e: self._active_keys.add("right"))
        self.btn_right.bind("<ButtonRelease-1>", lambda e: (self._active_keys.discard("right"), self._stop_if_idle()))

        self.btn_back = tk.Button(pad, text="▼", bg=self.BTN_NAV, fg=self.FG, **btn_cfg)
        self.btn_back.grid(row=2, column=1, padx=4, pady=4)
        self.btn_back.bind("<ButtonPress-1>",   lambda e: self._active_keys.add("back"))
        self.btn_back.bind("<ButtonRelease-1>",  lambda e: (self._active_keys.discard("back"), self._stop_if_idle()))

        # ── Speed sliders ──────────────────────────────────────
        sliders = tk.Frame(root, bg=self.BG)
        sliders.grid(row=3, column=0, columnspan=3, padx=20, pady=10)

        tk.Label(sliders, text="Linear Speed (m/s)", bg=self.BG, fg=self.FG,
                 font=("Helvetica", 9)).grid(row=0, column=0, sticky="w")
        self.linear_var = tk.DoubleVar(value=0.3)
        self.linear_slider = tk.Scale(
            sliders, from_=0.05, to=1.0, resolution=0.05,
            orient="horizontal", variable=self.linear_var,
            bg=self.CARD, fg=self.FG, troughcolor=self.SLIDER_TROUGH,
            highlightthickness=0, length=220, showvalue=True
        )
        self.linear_slider.grid(row=1, column=0, pady=2)

        tk.Label(sliders, text="Angular Speed (rad/s)", bg=self.BG, fg=self.FG,
                 font=("Helvetica", 9)).grid(row=2, column=0, sticky="w")
        self.angular_var = tk.DoubleVar(value=0.8)
        self.angular_slider = tk.Scale(
            sliders, from_=0.1, to=2.0, resolution=0.1,
            orient="horizontal", variable=self.angular_var,
            bg=self.CARD, fg=self.FG, troughcolor=self.SLIDER_TROUGH,
            highlightthickness=0, length=220, showvalue=True
        )
        self.angular_slider.grid(row=3, column=0, pady=2)

        # ── Live readout ────────────────────────────────────────
        self.readout_var = tk.StringVar(value="linear: 0.00  angular: 0.00")
        tk.Label(
            root, textvariable=self.readout_var, bg=self.CARD, fg=self.BTN_FWD,
            font=("Courier", 11, "bold"), pady=6, padx=10,
            relief="flat", width=30
        ).grid(row=4, column=0, columnspan=3, pady=(0, 6))

        # ── Keyboard hint ───────────────────────────────────────
        tk.Label(
            root,
            text="Arrow keys work anywhere in this window\nSpace = Stop",
            bg=self.BG, fg="#888888", font=("Helvetica", 8)
        ).grid(row=5, column=0, columnspan=3, pady=(0, 12))

    # ── Key bindings ─────────────────────────────────────────────────────
    def _bind_keys(self):
        self.root.bind("<KeyPress-Up>",    lambda e: self._active_keys.add("fwd"))
        self.root.bind("<KeyRelease-Up>",  lambda e: self._active_keys.discard("fwd"))
        self.root.bind("<KeyPress-Down>",  lambda e: self._active_keys.add("back"))
        self.root.bind("<KeyRelease-Down>",lambda e: self._active_keys.discard("back"))
        self.root.bind("<KeyPress-Left>",  lambda e: self._active_keys.add("left"))
        self.root.bind("<KeyRelease-Left>",lambda e: self._active_keys.discard("left"))
        self.root.bind("<KeyPress-Right>", lambda e: self._active_keys.add("right"))
        self.root.bind("<KeyRelease-Right>",lambda e: self._active_keys.discard("right"))
        self.root.bind("<space>",          lambda e: self._stop())

    # ── Key repeat loop ───────────────────────────────────────────────────
    def _key_loop(self):
        lin = self.linear_var.get()
        ang = self.angular_var.get()
        l, a = 0.0, 0.0
        if "fwd"   in self._active_keys: l =  lin
        if "back"  in self._active_keys: l = -lin
        if "left"  in self._active_keys: a =  ang
        if "right" in self._active_keys: a = -ang
        if self._active_keys:
            self._linear = l
            self._angular = a
            self._push()
        self.root.after(100, self._key_loop)

    # ── Velocity helpers ─────────────────────────────────────────────────
    def _stop_if_idle(self):
        """Stop the robot only if NO other direction key/button is still held."""
        if not self._active_keys:
            self._stop()

    def _stop(self):
        self._active_keys.clear()
        self._linear = 0.0
        self._angular = 0.0
        self._push()

    def _push(self):
        self.node.set_velocity(self._linear, self._angular)
        self.readout_var.set(
            f"linear: {self._linear:+.2f}  angular: {self._angular:+.2f}"
        )

    # ── Main loop ────────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()
        self._stop()  # zero-out on close


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
def main():
    rclpy.init(args=sys.argv)
    node = CmdVelPublisher()

    # Spin ROS in background
    ros_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    ros_thread.start()

    # Run GUI in main thread (Tkinter requirement)
    gui = SteeringGUI(node)
    gui.run()

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

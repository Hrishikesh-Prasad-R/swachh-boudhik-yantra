# ROS 2 Humble + Navigation2 — Windows GPU System Dependency Checklist

> **Target Machine:** Windows 11, NVIDIA RTX A6000, Python 3.10.7
> **ROS 2 Distribution:** Humble Hawksbill (LTS, supported through May 2027)
> **Architecture:** amd64 (x86_64)

---

## Phase 1: System Prerequisites

These must be installed BEFORE ROS 2:

| # | Dependency | Version | Purpose | Install Method |
|---|---|---|---|---|
| 1 | **Chocolatey** | Latest | Windows package manager (like apt for Linux) | PowerShell one-liner |
| 2 | **Visual Studio 2019 or 2022** | Community/BuildTools | C++ compiler needed to build ROS 2 packages from source | choco or manual |
| 3 | **CMake** | ≥ 3.22 | Build system used by all ROS 2 packages | choco |
| 4 | **Git** | Latest | Version control, needed by colcon/rosdep | choco |
| 5 | **Python 3.10** | 3.10.x | ✅ Already installed | — |
| 6 | **OpenSSL** | 1.1.x | Secure communication for DDS middleware | choco |
| 7 | **Visual C++ Redistributable** | 2015–2022 | Runtime libraries for compiled C++ code | choco |
| 8 | **Qt5** | 5.15.x | GUI framework required by RViz2 visualization | choco or manual |
| 9 | **Graphviz** | Latest | Graph visualization (used by rqt tools) | choco |

---

## Phase 2: ROS 2 Humble Core

| # | Component | Details |
|---|---|---|
| 1 | **ROS 2 Humble Desktop** | Full binary release (zip) from https://github.com/ros2/ros2/releases — includes rclpy, rclcpp, rviz2, rqt, tf2, std_msgs, sensor_msgs, geometry_msgs, nav_msgs |
| 2 | **Environment Setup** | Extract zip → run `local_setup.ps1` to configure PATH and environment variables |
| 3 | **rosdep** | `pip install rosdep` — dependency resolver for ROS packages |
| 4 | **colcon** | `pip install colcon-common-extensions` — ROS 2 build tool |
| 5 | **vcstool** | `pip install vcstool` — version control tool for managing multiple repos |
| 6 | **Fast-DDS** | Bundled with ROS 2 Humble binary — default DDS middleware |

---

## Phase 3: Navigation2 Stack

These are the Nav2 packages needed for autonomous navigation:

| # | Package | Purpose |
|---|---|---|
| 1 | **nav2_bringup** | Launch files and configuration for the full Nav2 stack |
| 2 | **nav2_bt_navigator** | Behavior tree-based navigation decision engine |
| 3 | **nav2_controller** | Local trajectory controller (DWB / Regulated Pure Pursuit) |
| 4 | **nav2_planner** | Global path planner (NavFn / Smac) |
| 5 | **nav2_costmap_2d** | Obstacle costmap generation from sensor data |
| 6 | **nav2_recoveries** | Recovery behaviors (spin, backup, wait) |
| 7 | **nav2_lifecycle_manager** | Manages lifecycle of all Nav2 nodes |
| 8 | **nav2_map_server** | Loads and serves pre-built maps |
| 9 | **nav2_amcl** | Adaptive Monte Carlo Localization (where-am-I on a known map) |
| 10 | **slam_toolbox** | Real-time SLAM (Simultaneous Localization and Mapping) |
| 11 | **robot_localization** | EKF/UKF sensor fusion (IMU + odometry → refined pose) |

> **Note:** Nav2 packages may not all be in the Humble binary zip. If missing, they need to be built from source using `colcon build` inside a ROS 2 workspace.

---

## Phase 4: Communication & Integration

| # | Package | Purpose |
|---|---|---|
| 1 | **micro_ros_agent** | Bridges micro-ROS on Arduino ↔ ROS 2 topics on the PC |
| 2 | **rosbridge_suite** | WebSocket bridge (optional, for web dashboard) |
| 3 | **tf2_ros** | Transform tree management (coordinate frames) |
| 4 | **robot_state_publisher** | Publishes URDF robot model to the TF tree |
| 5 | **joint_state_publisher** | Publishes joint states for robot arm visualization |

---

## Phase 5: Python Packages (pip)

| # | Package | Purpose |
|---|---|---|
| 1 | **colcon-common-extensions** | Builds ROS 2 workspaces |
| 2 | **rosdep** | Resolves ROS package dependencies |
| 3 | **vcstool** | Multi-repo VCS management |
| 4 | **lark** | Parser used internally by ROS 2 launch system |
| 5 | **numpy** | ✅ Already installed |
| 6 | **pyyaml** | ✅ Already installed |
| 7 | **opencv-python** | ✅ Already installed |
| 8 | **transforms3d** | 3D rotation/translation math for TF2 |
| 9 | **netifaces** | Network interface discovery |

---

## Phase 6: Verification Tests

| # | Test | Expected Result |
|---|---|---|
| 1 | `ros2 --version` | Prints `ros2 version 0.x.x` |
| 2 | `ros2 topic list` | Prints `/rosout` and `/parameter_events` |
| 3 | `ros2 run demo_nodes_cpp talker` | Publishes "Hello World" messages |
| 4 | `ros2 run demo_nodes_py listener` | Receives and prints messages from talker |
| 5 | `rviz2` | Opens RViz2 GUI window |
| 6 | `ros2 launch nav2_bringup navigation_launch.py` | Nav2 stack launches (may error without robot, but should load) |
| 7 | `python -c "import rclpy; print('rclpy OK')"` | Confirms Python ROS 2 bindings work |

---

## Important Notes

1. **Internet Required:** The GPU PC needs internet access. Use the RPi NAT forwarding we set up earlier (RPi shares WiFi → Ethernet to PC).
2. **Admin Rights:** All installation steps require Administrator PowerShell.
3. **Disk Space:** Full ROS 2 Humble + Nav2 requires ~5–8 GB.
4. **Reboot:** A system reboot is recommended after Phase 1 prerequisites.
5. **Environment Sourcing:** Every new PowerShell window must run `C:\dev\ros2_humble\local_setup.ps1` before using ROS 2 commands.

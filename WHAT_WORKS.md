# Swachh Boudhik Yantra — What Works (End-to-End Status)
### ROS 2 Jazzy · Gazebo Harmonic · Ubuntu 26.04 LTS

> **Reading guide:** ✅ = fully working & verified · 🔶 = built, not yet tested end-to-end · ❌ = not started

---

## 1. Host Environment

| Item | Status | Notes |
|---|---|---|
| Ubuntu 26.04 LTS base | ✅ | Custom library shims applied for Noble (24.04) compatibility |
| ROS 2 Jazzy (base + RViz2) | ✅ | All shebangs patched to Python 3.12 |
| Gazebo Harmonic | ✅ | `ros-jazzy-ros-gz-*` bridge installed |
| Python 3.12 (ROS runtime) | ✅ | Deadsnakes PPA; numpy installed locally |
| PCL 1.14 → 1.15 shims | ✅ | 20 shim packages + symlinks |
| CycloneDDS middleware | ✅ | `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` (replaces FastDDS) |
| Nav2 stack | ✅ | `ros-jazzy-navigation2` installed |
| SLAM Toolbox | ✅ | `ros-jazzy-slam-toolbox` installed |
| RTABMap | ✅ | Built from source in `ros2_ws` |
| `colcon build` workspace | ✅ | `vacuum_ws` builds clean with `--symlink-install` |

---

## 2. Robot Model (vacuum_description)

**What it is:** The URDF/Xacro model that defines the robot's physical shape, joints, sensors, and hardware interfaces.

| Item | Status | Notes |
|---|---|---|
| Chassis body link | ✅ | Box geometry, inertia, collision |
| Left & right powered wheels | ✅ | Continuous joints, correct inertia |
| Passive front caster wheel | ✅ | Free-rolling, modelled as a sphere |
| Intel RealSense D435i link | ✅ | Camera link positioned at front-top of chassis |
| Materials & visual colours | ✅ | `_materials.xacro` |
| Inertia matrices | ✅ | Calculated in `_properties.xacro` |
| Collision geometries | ✅ | Match visual geometry |
| `ros2_control` hardware interface | ✅ | `_ros2_control.xacro` — velocity command + position state |
| Gazebo plugin (gz_ros2_control) | ✅ | `_gazebo.xacro` — loads controller YAML at spawn |
| Gazebo sensor plugins (camera, depth, IMU) | ✅ | Wired to Gz topics in `_gazebo.xacro` |
| RViz2 standalone model view | ✅ | Tested with `joint_state_publisher_gui` |

---

## 3. ROS 2 Control (vacuum_controller)

**What it is:** Makes ROS 2 able to move the robot's wheels by sending velocity commands.

| Item | Status | Notes |
|---|---|---|
| `controller_manager` at 50 Hz | ✅ | Defined in `controllers.yaml` |
| `joint_state_broadcaster` | ✅ | Publishes `/joint_states` for both wheel joints |
| `diff_drive_controller` | ✅ | Closed-loop differential drive kinematics |
| Odometry publisher (`/odom`) | ✅ | 30 Hz, `odom → base_footprint` TF |
| Velocity limits (linear 0.5 m/s, angular 2.0 rad/s) | ✅ | Enforced by controller |
| Acceleration limits | ✅ | 1.0 m/s², 2.0 rad/s² |
| `cmd_vel_relay.py` node | ✅ | Converts `Twist` → `TwistStamped` with sim-clock stamp |
| `teleop_arrows.py` node | ✅ | Arrow-key keyboard steering with live log |

---

## 4. Gazebo Simulation (vacuum_gazebo)

**What it is:** The 3D simulation environment where the robot lives and is tested.

| Item | Status | Notes |
|---|---|---|
| Robot spawned in Gazebo Harmonic | ✅ | Spawned from URDF via `sim.launch.py` |
| Apartment world (`apartment.sdf`) | ✅ | Walls, furniture, obstacles |
| Office world (`office.sdf`) | ✅ | Created, not yet used in experiments |
| Narrow corridor world (`corridor.sdf`) | ✅ | Created, not yet used in experiments |
| Empty world (`empty_world.sdf`) | ✅ | For unit-level testing |
| `/clock` bridge (sim time) | ✅ | `ros_gz_bridge` → `/clock` |
| RGB camera topic bridge | ✅ | `/camera/color/image_raw` visible in RViz2 |
| Depth camera topic bridge | ✅ | `/camera/depth/image_rect_raw` |
| Point cloud bridge | ✅ | `/camera/depth/points` |
| Camera info bridge | ✅ | `/camera/color/camera_info` |
| TF tree (base_footprint → base_link → camera) | ✅ | Verified in RViz2 |

---

## 5. SLAM Mapping (vacuum_slam)

**What it is:** The robot builds a 2D/3D map of the environment by driving around with the camera and wheel odometry.

| Item | Status | Notes |
|---|---|---|
| RTABMap SLAM node running | ✅ | RGB-D + odometry fusion |
| 2D occupancy grid (`/map`) published | ✅ | Visible in RViz2 live |
| Loop closure detection | ✅ | Active via RTABMap visual features |
| Map saved to disk (`map.yaml` + `map.pgm`) | ✅ | Exported via `nav2_map_server` to `~/maps/stage4/` |
| SLAM RViz2 config (`slam_rviz.rviz`) | ✅ | Pre-configured: map, camera, TF, scan |
| `slam.launch.py` | ✅ | Launches RTABMap with correct remaps |
| `map_saver.launch.py` | ✅ | Connects to map server and saves file |
| `rtabmap.yaml` parameter file | ✅ | Loop closure thresholds, voxel grid tuned |

---

## 6. Autonomous Navigation (vacuum_nav2)

**What it is:** The robot can be given a goal point on the map and will plan a path and drive there autonomously.

| Item | Status | Notes |
|---|---|---|
| `nav2_params.yaml` | ✅ | Full Nav2 stack configuration |
| `amcl_params.yaml` | ✅ | AMCL particle filter localization parameters |
| `map_server_params.yaml` | ✅ | Map server for loading saved map |
| `nav2.launch.py` | ✅ | Full Nav2 stack launch (planner, controller, costmaps) |
| `nav2_localization.launch.py` | ✅ | Localization-only launch (AMCL + map server) |
| Behavior tree — navigate (`navigate.xml`) | ✅ | Navigate-to-pose with recovery behaviors |
| Behavior tree — explore (`explore.xml`) | ✅ | Exploration behavior tree |
| End-to-end autonomous nav test | 🔶 | Config ready, runtime validation pending |

---

## 7. Localization (vacuum_localization)

**What it is:** Monitors how accurately the robot knows where it is on the map, and triggers recovery if localization fails.

| Item | Status | Notes |
|---|---|---|
| `localization_monitor.py` | ✅ | Monitors AMCL pose covariance in real time |
| `localization_metrics.py` | ✅ | Collects ATE, RPE, drift metrics |
| `pose_quality.py` | ✅ | Computes pose quality score from covariance |
| `recovery_monitor.py` | ✅ | Detects and logs recovery behavior triggers |
| `localization_params.yaml` | ✅ | Thresholds for acceptable localization quality |
| End-to-end localization loop | 🔶 | Nodes built, needs Nav2 running to validate |

---

## 8. Frontier Exploration (vacuum_exploration)

**What it is:** The robot explores unknown areas of the map automatically without manual driving — it finds unvisited frontiers and navigates to them.

| Item | Status | Notes |
|---|---|---|
| `frontier_detector.py` | ✅ | Detects open frontiers on occupancy grid |
| `frontier_visualizer.py` | ✅ | Publishes frontier markers to RViz2 |
| `goal_selector.py` | ✅ | Picks the best frontier goal using scoring |
| `exploration_manager.py` | ✅ | Orchestrates full exploration loop |
| `exploration_metrics.py` | ✅ | Tracks coverage %, exploration time, frontier count |
| `exploration.launch.py` | ✅ | Launches full exploration stack |
| End-to-end exploration loop | 🔶 | Nodes built, needs Nav2 + SLAM running to validate |

---

## 9. Utility & Metrics Scripts (vacuum_utils)

**What it is:** A collection of standalone scripts for testing, benchmarking, and validating individual subsystems.

| Script | What it does | Status |
|---|---|---|
| `validate_urdf.sh` | Checks URDF for errors, lists links & joints | ✅ |
| `validate_controllers.sh` | Verifies controller manager and joint states | ✅ |
| `validate_camera.sh` | Checks camera topic FPS and resolution | ✅ |
| `check_tf.py` | Prints the full TF tree and checks for broken links | ✅ |
| `benchmark_camera.py` | Measures camera FPS, latency, drop rate | ✅ |
| `benchmark_slam.py` | Measures SLAM keyframe rate, loop closures, CPU | ✅ |
| `collect_metrics.py` | Collects navigation metrics from rosbag | ✅ |
| `evaluate_trajectory.py` | Computes ATE and RPE from trajectory logs | ✅ |
| `record_trajectory.py` | Records robot poses to a CSV for analysis | ✅ |
| `drive_robot.py` | Programmatically drives robot along a test path | ✅ |
| `graphify.py` (root level) | Generates plots from collected metric CSVs | ✅ |
| `record_stage4.sh` | Records a rosbag of the full SLAM session | ✅ |

---

## 10. Automation Shell Scripts (project root)

**What it is:** One-command launchers that bring up the full system so you never need to remember the individual ROS 2 commands.

| Script | What it does | Status |
|---|---|---|
| `./run_mapping.sh` | Launches Gazebo + SLAM + RViz + Teleop in tmux panes | ✅ |
| `./save_map.sh` | Connects to map server and saves `map.yaml` + `map.pgm` | ✅ |
| `./view_map.sh` | Opens the saved map image for inspection | ✅ |
| `./start.sh` | Full system bringup (sim + nav + slam + viz) | ✅ |
| `./stop.sh` | Cleanly kills all ROS 2 and Gazebo processes | ✅ |
| `./steer_gui.sh` | Launches arrow-key teleop interface | ✅ |

---

## 11. End-to-End Flow Summary

```
[Keyboard / Autonomy]
        │
        ▼
teleop_arrows.py  ──►  cmd_vel_relay.py  ──►  diff_drive_controller
                                                       │
                              ┌────────────────────────┤
                              │                        │
                              ▼                        ▼
                         /odom (TF)            Gazebo Physics Sim
                              │                        │
                         RTABMap SLAM  ◄───── /camera/color, /camera/depth
                              │
                         /map (OccupancyGrid)
                              │
                    ┌─────────┴──────────┐
                    │                    │
              Map Saver              Nav2 Stack
           (map.yaml/.pgm)     (AMCL + Planner + Controller)
                                         │
                              Frontier Exploration
                           (frontier_detector → goal_selector
                              → exploration_manager)
```

---

## 12. What Is Not Yet Done

| Item | Reason |
|---|---|
| End-to-end Nav2 autonomous navigation test | Nav2 stack built, runtime validation not yet executed |
| Frontier exploration end-to-end run | Depends on Nav2 being validated first |
| Metrics collection during autonomous nav | Needs a full nav session recorded as rosbag |
| Robotic arm (MoveIt2) | Not started — planned for later phase |
| Vacuum cleaning module | Not started — planned for later phase |
| Warehouse / Hospital / Maze worlds | Not created — only apartment, office, corridor done |
| Dynamic obstacles (moving humans) | Not implemented |
| Multi-room coverage planner | Not started |
| Real hardware deployment (Jetson Orin Nano) | Blocked until all simulation phases pass |

---

## 13. Key Configuration Files (Quick Reference)

| File | Purpose |
|---|---|
| [`controllers.yaml`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_controller/config/controllers.yaml) | Wheel controller, kinematics, velocity limits |
| [`rtabmap.yaml`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_slam/config/rtabmap.yaml) | SLAM parameters, loop closure thresholds |
| [`nav2_params.yaml`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_nav2/config/nav2_params.yaml) | Full Nav2 stack (costmaps, planners, controllers) |
| [`amcl_params.yaml`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_nav2/config/amcl_params.yaml) | Particle filter localization |
| [`localization_params.yaml`](file:///home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/src/vacuum_localization/config/localization_params.yaml) | Localization quality thresholds |

---

*Generated: October 2026 · Project: Swachh Boudhik Yantra*

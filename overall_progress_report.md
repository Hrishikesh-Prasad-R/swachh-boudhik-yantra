# Swachh Boudhik Yantra — Overall Project Progress Report
### ROS 2 Jazzy | Gazebo Harmonic | Jetson Orin Nano Target

---

## 1. Executive Summary
This report summarizes the entire development lifecycle from "Day 0" to the current state. The overarching goal is to build a production-quality autonomous indoor vacuum cleaning robot. We have successfully completed all core modeling, control, simulation, and mapping stages. The robot is fully operational in Gazebo Harmonic, and a high-resolution 2D map of the apartment environment has been successfully exported.

**Current Status:** **Stage 4 (SLAM Mapping) COMPLETE.** Ready for Stage 5 (Autonomous Navigation).

---

## 2. Phase-by-Phase Breakdown

### ✅ Phase 0: Environment & Architecture Setup
* **Objective:** Validate the host environment and establish the architecture.
* **Achievements:**
  * Validated Ubuntu 26.04 LTS host with ROS 2 Jazzy and Gazebo Harmonic.
  * Audited the system for RealSense dependencies, DDS implementations, and Nav2 stacks.
  * Established the strict "Simulation First" development philosophy.
  * Set up the modular `vacuum_ws` workspace structure.

### ✅ Phase 1: URDF & Robot Modeling
* **Objective:** Design the robot's physical characteristics, links, and joints.
* **Achievements:**
  * Built the robot's Xacro/URDF model from scratch.
  * Configured a differential drive setup (two rear powered wheels, one passive front caster).
  * Modeled the vacuum chassis and integrated the RealSense D435i RGB-D camera sensor link.
  * Applied visual materials, inertia matrices, and collision geometries.
  * Tested the standalone model in RViz using `joint_state_publisher_gui`.

### ✅ Phase 2: Hardware Interfaces & ROS 2 Control
* **Objective:** Allow ROS 2 to send velocity commands to the robot's wheels.
* **Achievements:**
  * Implemented `ros2_control` with `ign_ros2_control` (Gazebo Harmonic plugin).
  * Configured the `diff_drive_controller` to handle differential steering kinematics.
  * Configured the `joint_state_broadcaster` to publish `/tf` transforms.
  * Established the strict requirement of `TwistStamped` messages for Jazzy's controller manager.

### ✅ Phase 3: Gazebo Simulation & Sensors
* **Objective:** Spawn the robot in a realistic environment and capture sensor data.
* **Achievements:**
  * Created the custom `apartment.sdf` world featuring walls, furniture, and obstacles.
  * Spawned the URDF robot inside Gazebo Harmonic.
  * Configured the `ros_gz_bridge` to stream Gazebo topics (`/clock`, `/camera/color`, `/camera/depth`) into the native ROS 2 ecosystem.
  * Verified sensor outputs (Point Clouds and RGB streams) inside RViz2.

### ✅ Phase 4: SLAM Mapping & Map Generation
* **Objective:** Enable the robot to scan the environment and build a usable navigation map.
* **Achievements:**
  * **Middleware Swap:** Transitioned from FastRTPS to `rmw_cyclonedds_cpp` to fix RealSense dependency collisions/crashes.
  * **RTAB-Map Integration:** Implemented 3D RGB-D + Odometry SLAM using RTAB-Map.
  * **Command Relay:** Wrote a custom `cmd_vel_relay.py` to automatically stamp and bridge teleop commands to the controller.
  * **Custom Teleop:** Wrote a custom keyboard steering node (`teleop_arrows.py`).
  * **Mapping Output:** Successfully drove the robot around the apartment and exported a high-quality 2D occupancy grid (`map.yaml` and `map.pgm`) using `nav2_map_server`.

---

## 3. Automation Scripts Developed
To enforce reproducibility and make testing easy, the following bash scripts were developed at the workspace root:
* `./run_mapping.sh`: Automatically brings up Gazebo, SLAM, RViz, and Teleop in a multi-pane environment.
* `./save_map.sh`: Automatically connects to the map server and exports the generated map to `~/maps/stage4/`.
* `./view_map.sh`: Instantly opens the saved map image for visual inspection.

---

## 4. Next Steps: Phase 5 (Autonomous Navigation)
With the map successfully generated and verified, the next phase will introduce **Nav2**.
* **Goal:** Allow the user to click a point on the map, and the robot will autonomously plan a path and drive to it while avoiding dynamic obstacles.
* **Tasks:**
  * Create the `vacuum_nav2` package.
  * Configure Global Planners (e.g., Smac Hybrid A*) and Local Planners (e.g., MPPI).
  * Configure Costmaps to inflate the obstacles seen on the map.
  * Write the `nav2.launch.py` file to localize the robot and start path planning.

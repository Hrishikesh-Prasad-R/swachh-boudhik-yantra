# ROS 2 Jazzy — Software Stack Specifications
### Live-Verified Specifications for Q1 Paper Methodology Section

This document lists the exact software versions, middleware configurations, system libraries, and benchmarking tools currently installed and running on your HP Z4 G5 Workstation. You can copy and paste this table directly into the **Methodology / Experimental Setup** section of your Q1 manuscript.

---

## 🛠️ Main Software & OS Stack

| Component | Software / Package | Version | Notes / Details |
|---|---|---|---|
| **Operating System** | Ubuntu Linux | 26.04 LTS (Resolute) | 64-bit architecture |
| **Linux Kernel** | Linux Kernel | `7.0.0-22-generic` | Real-time / low-latency capable |
| **ROS Distribution** | ROS 2 Jazzy Jalisco | `Jazzy` | Long-Term Support (LTS) release |
| **ROS C++ Client Library** | `rclcpp` | `28.1.18` | Core execution framework |
| **ROS Python Client Library**| `rclpy` | `7.1.11` | Scripting and testing framework |
| **DDS / Transport Layer** | Eclipse Cyclone DDS | `0.11.0` (impl) | Preferred transport for Nav2 (`rmw_cyclonedds_cpp`) |
| **DDS / Default Transport** | eProsima Fast DDS | `2.14.6` (impl) | System default wrapper (`rmw_fastrtps_cpp` version `8.4.3`) |
| **Simulation Platform** | Gazebo Sim (Harmonic) | `8.11.0` | Formerly Ignition Gazebo |
| **ROS-Gazebo Bridge** | `ros_gz_bridge` | `1.0.22` | Direct Gazebo Transport $\leftrightarrow$ ROS 2 topic translation |

---

## 🧭 SLAM & Navigation Stack

| Component | ROS 2 Package | Version | Implementation Details |
|---|---|---|---|
| **3D SLAM Engine** | `rtabmap` (Core Library) | `0.23.7` | Built from source (`jazzy-devel` branch) |
| **3D SLAM ROS Wrapper** | `rtabmap_ros` | `0.23.7` | Built from source (`ros2` branch) |
| **2D SLAM Engine** | `slam_toolbox` | `2.8.5` | Asynchronous/Synchronous LiDAR mapping |
| **Alternative 2D SLAM** | `cartographer_ros` | `2.0.9003` | Google Cartographer ROS 2 wrapper |
| **Navigation Stack** | Nav2 (`navigation2`) | `1.3.12` | Behavioral-tree-based navigation |
| **Global Path Planners** | `nav2_navfn_planner` | `1.3.12` | Dijkstra & A* grid-based path planners |
| **Hybrid Path Planner** | `nav2_smac_planner` | `1.3.12` | Hybrid A* (Reeds-Shepp/Dubins models) |
| **Any-Angle Planner** | `nav2_theta_star_planner` | `1.3.12` | Theta* path planner |
| **Local Planner (DWB)** | `nav2_dwb_controller` | `1.3.12` | Dynamic Window Approach variant |
| **Local Planner (MPPI)** | `nav2_mppi_controller` | `1.3.12` | Model Predictive Path Integral controller |
| **Sensor Fusion / EKF** | `robot_localization` | `3.8.3` | Dual Extended Kalman Filter state estimator |

---

## 📷 Sensors & Coordinate Math

| Component | Software / Package | Version | Notes / Details |
|---|---|---|---|
| **RealSense Driver (Apt)** | `ros-jazzy-realsense2-camera`| `4.58.1` | Native wrapper for Intel RealSense cameras |
| **RealSense SDK** | `librealsense2` | `2.58.1` | Intel RealSense SDK backend |
| **Simulated RGB-D Sensor** | Gazebo `rgbd_camera` | Native | Emulated Intel RealSense D435i |
| **Coordinate Transforms** | `tf2_ros` | `0.36.20` | Dynamic transform tree manager |
| **Kinematics / Math** | Orocos KDL | `3.4.0` | Kinematics and Dynamics Library |
| **Vector Algebra** | Eigen3 | `3.4.0` | Matrix and vector arithmetic library |

---

## 📊 System Libraries & Development Tools

| Component | Software / Package | Version | Role in the Stack |
|---|---|---|---|
| **Computer Vision** | OpenCV | `4.10.0` | Image processing and feature matching in RTAB-Map |
| **Point Cloud Processing** | PCL (Point Cloud Library) | `1.15.1` | 3D filtering and voxelization in SLAM |
| **C++ Helper Classes** | Boost | `1.90.0` | System-level tasks and multi-threading |
| **C++ Compiler** | GCC | `15.2.0` | Native compilation |
| **Build Tool** | CMake | `4.2.3` | Compilation configuration tool |
| **ROS Build Tool** | `colcon-core` | `0.20.1` | ROS 2 workspace compiler |

---

## 📈 Benchmarking & Analysis (Python Environment)

| Component | Python Package | Version | Purpose in Experiments |
|---|---|---|---|
| **Python Interpreter** | Python | `3.14.4` | Script execution environment |
| **Trajectory Evaluation** | `evo` | `1.36.5` | Computes ATE, RPE, and generates plots |
| **Bag Parser** | `rosbags` | `0.11.3` | Reads MCAP/SQLite bags directly in Python |
| **Scientific Computing** | SciPy | `1.18.0` | Statistical calculations |
| **Data Analysis** | Pandas | `3.0.3` | Log file sorting, formatting, and metrics tables |
| **Plotting Engine** | Matplotlib | `3.11.0` | Figure generation for publication |
| **Statistical Plotting** | Seaborn | `0.13.2` | Clean, academic comparative visualization |
| **Numerical Math** | NumPy | `2.3.5` | Matrix-level array calculations |

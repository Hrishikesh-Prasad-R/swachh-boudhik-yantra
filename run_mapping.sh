#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_mapping.sh
# ─────────────────────────────────────────────────────────────────────────────
# Automatically launches the complete autonomous vacuum robot mapping pipeline:
#   1. Gazebo Harmonic simulation (apartment world)
#   2. RTAB-Map SLAM mapping node
#   3. RViz2 (2D map + camera feed)
#   4. rtabmap_viz (3D point cloud + loop closure graph)
#   5. teleop_twist_keyboard (in the foreground)
#
# Cleans up all background processes automatically when you exit the script!
# ─────────────────────────────────────────────────────────────────────────────

# Exit immediately if any command fails
set -e

echo -e "\033[1;36m======================================================="
echo -e "  Swachh Boudhik Yantra — Autonomous Mapping Session  "
echo -e "=======================================================\033[0m"

# ── 1. Clean up existing processes ─────────────────────────────────
echo "Cleaning up any running Gazebo/ROS processes..."
killall -9 gz sim server gz sim gui ruby parameter_bridge rtabmap rtabmap_viz rviz2 teleop_twist_keyboard 2>/dev/null || true
sleep 1

# ── 2. Setup ROS2 Environment ──────────────────────────────────────
echo "Sourcing workspace environments..."
source /opt/ros/jazzy/setup.bash
source /home/bmscecse/ros2_ws/install/setup.bash
source /home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/install/setup.bash

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export LD_LIBRARY_PATH=/home/bmscecse/ros2_ws/install/lib:$LD_LIBRARY_PATH
export PATH=/home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/bin:$PATH

# ── 3. Define Cleanup Trap on Exit ──────────────────────────────────
# Automatically kills all background processes launched by this script when it exits
PIDS=()
cleanup() {
    echo -e "\n\033[1;33mShutting down all mapping processes and cleaning up...\033[0m"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    killall -9 gz sim server gz sim gui ruby parameter_bridge rtabmap rtabmap_viz rviz2 2>/dev/null || true
    echo -e "\033[1;32mCleanup complete. Session ended.\033[0m"
}
trap cleanup EXIT

# ── 4. Launch Gazebo Simulation ────────────────────────────────────
echo "Launching Gazebo simulation (apartment world)..."
python3.12 /opt/ros/jazzy/bin/ros2 launch vacuum_bringup sim.launch.py world:=apartment use_rviz:=false > /tmp/sim_launch.log 2>&1 &
SIM_PID=$!
PIDS+=("$SIM_PID")

echo "Waiting 10s for simulation and controller manager to start..."
sleep 10

# ── 5. Launch RTAB-Map SLAM Node ───────────────────────────────────
echo "Launching RTAB-Map SLAM node..."
python3.12 /opt/ros/jazzy/bin/ros2 launch vacuum_slam slam.launch.py environment:=apartment use_rviz:=false > /tmp/slam_launch.log 2>&1 &
SLAM_PID=$!
PIDS+=("$SLAM_PID")

echo "Waiting 5s for SLAM initialization..."
sleep 5

# ── 6. Launch RViz2 Visualizer ─────────────────────────────────────
echo "Launching RViz2..."
python3.12 /opt/ros/jazzy/bin/ros2 run rviz2 rviz2 \
  -d /home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/install/vacuum_bringup/share/vacuum_bringup/config/rviz_config.rviz > /tmp/rviz2.log 2>&1 &
RVIZ_PID=$!
PIDS+=("$RVIZ_PID")

# ── 7. Launch RTAB-Map standalone 3D visualizer ───────────────────
echo "Launching rtabmap_viz..."
python3.12 /opt/ros/jazzy/bin/ros2 run rtabmap_viz rtabmap_viz --ros-args \
  -r rgb/image:=/camera/color/image_raw \
  -r depth/image:=/camera/depth/image_rect_raw \
  -r rgb/camera_info:=/camera/color/camera_info \
  -r odom:=/odom > /tmp/rtabmap_viz.log 2>&1 &
VIZ_PID=$!
PIDS+=("$VIZ_PID")

# ── 8. Launch Keyboard Teleoperation (Foreground) ──────────────────
python3.12 /home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/install/vacuum_controller/lib/vacuum_controller/teleop_arrows.py


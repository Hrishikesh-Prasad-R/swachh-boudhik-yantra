#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# save_map.sh
# ─────────────────────────────────────────────────────────────────────────────
# Sours the environment and executes the map saver using python3.12 to bypass
# shebang conflicts on Ubuntu 26.04 workstation.
# ─────────────────────────────────────────────────────────────────────────────

# Exit immediately if any command fails
set -e

echo "Sourcing environments..."
source /opt/ros/jazzy/setup.bash
source /home/bmscecse/ros2_ws/install/setup.bash
source /home/bmscecse/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/install/setup.bash

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export LD_LIBRARY_PATH=/home/bmscecse/ros2_ws/install/lib:$LD_LIBRARY_PATH

echo "Ensuring output directory ~/maps/stage4 exists..."
mkdir -p ~/maps/stage4

echo "Running map saver..."
python3.12 /opt/ros/jazzy/bin/ros2 launch vacuum_slam map_saver.launch.py

echo -e "\n\033[1;32mMap successfully saved to ~/maps/stage4/map.yaml & ~/maps/stage4/map.pgm!\033[0m"

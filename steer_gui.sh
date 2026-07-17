#!/bin/bash
# ─────────────────────────────────────────────────────────────
# steer_gui.sh
# Launches the Tkinter robot steering GUI.
# Works alongside run_mapping.sh – no terminal focus needed.
# ─────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$SCRIPT_DIR/Simulation/vacuum_ws"
GUI="$WS/src/vacuum_controller/vacuum_controller/robot_steering_gui.py"

echo "─────────────────────────────────────────────"
echo "  Swachh Boudhik Yantra — Steering GUI"
echo "─────────────────────────────────────────────"
echo ""

source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
export PYTHONPATH="$WS/install/vacuum_controller/lib/python3.12/site-packages:$PYTHONPATH"

echo "Launching steering GUI..."
python3.12 "$GUI"

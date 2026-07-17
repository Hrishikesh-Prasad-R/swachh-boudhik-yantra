#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  start.sh — Swachh Boudhik Yantra
#
#  Usage:
#    ./start.sh          → manual teleoperation + mapping (Stage 4A)
#    ./start.sh explore  → autonomous frontier exploration (Stage 4B)
#    ./start.sh steer    → launch steering GUI only (attach to running session)
#
#  Modes:
#    [default] :  Gazebo + SLAM + RViz + Steering GUI (Stage 4A)
#    explore   :  Full autonomous stack via exploration.launch.py (Stage 4B)
#    steer     :  Steering GUI only (for attaching to an existing session)
# ═══════════════════════════════════════════════════════════════
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-manual}"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        Swachh Boudhik Yantra — START                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ────────────────────────────────────────────────────────────────
#  MODE: explore  →  Stage 4B Autonomous Frontier Exploration
# ────────────────────────────────────────────────────────────────
if [[ "$MODE" == "explore" ]]; then
    ENV="${2:-apartment}"
    echo "  Mode        : Autonomous Exploration (Stage 4B)"
    echo "  Environment : $ENV"
    echo ""
    echo "[1/1] Launching full exploration stack in new window..."
    echo "      (Gazebo → SLAM → Nav2 → Exploration nodes)"
    echo ""

    ptyxis --new-window -- bash -c "
        echo '╔══════════════════════════════════════════════════════╗'
        echo '║  Stage 4B: Autonomous Exploration                    ║'
        echo '║  Do NOT use the keyboard — robot drives itself.      ║'
        echo '╚══════════════════════════════════════════════════════╝'
        echo ''
        cd '$DIR'
        source /opt/ros/jazzy/setup.bash
        source Simulation/vacuum_ws/install/setup.bash
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
        export ROS_DOMAIN_ID=0
        ros2 launch vacuum_exploration exploration.launch.py environment:=$ENV
        exec bash
    " &

    echo "✅  Exploration launched!"
    echo ""
    echo "  Monitor coverage in real time:"
    echo "    ros2 topic echo /exploration/status"
    echo ""
    echo "  Save map when complete:"
    echo "    ./save_map.sh"
    echo ""
    exit 0
fi

# ────────────────────────────────────────────────────────────────
#  MODE: steer  →  Steering GUI only
# ────────────────────────────────────────────────────────────────
if [[ "$MODE" == "steer" ]]; then
    echo "  Mode : Steering GUI only (attach to existing session)"
    echo ""
    bash "$DIR/steer_gui.sh"
    exit 0
fi

# ────────────────────────────────────────────────────────────────
#  MODE: manual (default) →  Stage 4A Teleoperation Mapping
# ────────────────────────────────────────────────────────────────
echo "  Mode : Manual Teleoperation + Mapping (Stage 4A)"
echo ""
echo "[1/2] Opening Gazebo / SLAM / RViz window..."

ptyxis --new-window -- bash -c "
    echo '=== Gazebo | SLAM | RViz ==='
    cd '$DIR'
    bash run_mapping.sh
    exec bash
" &

echo "[2/2] Waiting 12 s for ROS stack to initialise..."
sleep 12

echo "      Opening Steering GUI window..."
ptyxis --new-window -- bash -c "
    echo '=== Robot Steering GUI ==='
    cd '$DIR'
    bash steer_gui.sh
    exec bash
" &

echo ""
echo "✅  Both windows launched."
echo "    • Drive from the Steering GUI window."
echo "    • Save map any time:  ./save_map.sh"
echo "    • View map:           ./view_map.sh"
echo ""

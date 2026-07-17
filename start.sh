#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  start.sh — Swachh Boudhik Yantra
#
#  Usage:
#    ./start.sh                    → manual teleoperation + mapping (Stage 4A)
#    ./start.sh explore [env]      → autonomous frontier exploration (Stage 4B)
#    ./start.sh navigate [env]     → AMCL localization + goal navigation (Stage 5)
#    ./start.sh steer              → steering GUI only (attach to running session)
#
#  Environments (for explore/navigate): apartment office room corridor warehouse
#
#  Modes:
#    [default]  :  Gazebo + SLAM + RViz + Steering GUI (Stage 4A)
#    explore    :  Full autonomous stack via exploration.launch.py (Stage 4B)
#    navigate   :  AMCL + Map Server + Nav2 via nav2_localization.launch.py (Stage 5)
#    steer      :  Steering GUI only
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
        export CYCLONEDDS_URI=file://'$DIR'/cyclone_dds.xml
        python3.12 /opt/ros/jazzy/bin/ros2 launch vacuum_exploration exploration.launch.py environment:=$ENV
        exec bash
    " &

    echo "✅  Exploration launched!"
    echo ""
    echo "  Monitor coverage in real time:"
    echo "    ros2 topic echo /exploration/status"
    echo ""
    echo "  Save map when done (WHILE SIM IS RUNNING):"
    echo "    ./save_map.sh $ENV"
    echo ""
    exit 0
fi

# ────────────────────────────────────────────────────────────────
#  MODE: navigate  →  Stage 5 AMCL Localization + Goal Navigation
# ────────────────────────────────────────────────────────────────
if [[ "$MODE" == "navigate" ]]; then
    ENV="${2:-apartment}"
    MAP_PATH="$HOME/maps/stage5/${ENV}.yaml"

    echo "  Mode        : Localization + Goal Navigation (Stage 5)"
    echo "  Environment : $ENV"
    echo "  Map         : $MAP_PATH"
    echo ""

    if [[ ! -f "$MAP_PATH" ]]; then
        echo "  ❌ Map not found: $MAP_PATH"
        echo ""
        echo "  Run exploration first, then save the map:"
        echo "    ./start.sh explore $ENV"
        echo "    ./save_map.sh $ENV"
        echo ""
        exit 1
    fi

    echo "[1/2] Launching Gazebo simulation window..."
    ptyxis --new-window -- bash -c "
        echo '=== Gazebo Simulation (Stage 5) ==='
        cd '$DIR'
        source /opt/ros/jazzy/setup.bash
        source Simulation/vacuum_ws/install/setup.bash
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
        export ROS_DOMAIN_ID=0
        export CYCLONEDDS_URI=file://'$DIR'/cyclone_dds.xml
        python3.12 /opt/ros/jazzy/bin/ros2 launch vacuum_bringup sim.launch.py use_sim_time:=true
        exec bash
    " &

    echo "[2/2] Waiting 14 s for simulation, then launching Nav2 + AMCL..."
    sleep 14

    ptyxis --new-window -- bash -c "
        echo '╔══════════════════════════════════════════════════════╗'
        echo '║  Stage 5: AMCL Localization + Goal Navigation        ║'
        echo '║  Use RViz "2D Pose Estimate" to initialise AMCL.     ║'
        echo '║  Use RViz "Nav2 Goal" to send navigation goals.      ║'
        echo '╚══════════════════════════════════════════════════════╝'
        cd '$DIR'
        source /opt/ros/jazzy/setup.bash
        source Simulation/vacuum_ws/install/setup.bash
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
        export ROS_DOMAIN_ID=0
        export CYCLONEDDS_URI=file://'$DIR'/cyclone_dds.xml
        python3.12 /opt/ros/jazzy/bin/ros2 launch vacuum_nav2 nav2_localization.launch.py \\
            map_path:=$MAP_PATH environment:=$ENV
        exec bash
    " &

    echo ""
    echo "✅  Navigation stack launching!"
    echo ""
    echo "  Workflow:"
    echo "    1. Wait for RViz to open (~30 s)"
    echo "    2. Click '2D Pose Estimate' → place arrow at robot spawn position"
    echo "    3. Watch particles converge (green cloud in RViz)"
    echo "    4. Click 'Nav2 Goal' → click anywhere on the map"
    echo ""
    echo "  Monitor localization:"
    echo "    ros2 topic echo /localization/status"
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

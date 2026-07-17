#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════════
#  save_map.sh — Swachh Boudhik Yantra
#
#  Usage:
#    ./save_map.sh              → ~/maps/stage4/map.pgm   (Stage 4A default)
#    ./save_map.sh apartment    → ~/maps/stage5/apartment.pgm
#    ./save_map.sh office       → ~/maps/stage5/office.pgm
#    ./save_map.sh room         → ~/maps/stage5/room.pgm
#
#  IMPORTANT: Run WHILE simulation + SLAM is still running.
#             Ctrl+C RTAB-Map BEFORE saving = empty/missing map.
# ═════════════════════════════════════════════════════════════════════════════
set -e

ENV_NAME="${1:-}"   # optional environment name argument

if [[ -n "$ENV_NAME" ]]; then
    OUTPUT_DIR="$HOME/maps/stage5"
    MAP_NAME="$ENV_NAME"
    STAGE="5"
else
    OUTPUT_DIR="$HOME/maps/stage4"
    MAP_NAME="map"
    STAGE="4"
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║             Swachh Boudhik Yantra — Map Saver        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Stage      : $STAGE"
echo "  Map name   : $MAP_NAME"
echo "  Output dir : $OUTPUT_DIR"
echo ""
echo "  ⚠️  RTAB-Map must be running (do not Ctrl+C before this completes)"
echo ""

source /opt/ros/jazzy/setup.bash
source "$HOME/Swachh_Boudhik_Yantra/Simulation/vacuum_ws/install/setup.bash"

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

mkdir -p "$OUTPUT_DIR"

echo "[saving] Running map_saver_cli..."
python3.12 /opt/ros/jazzy/bin/ros2 run nav2_map_server map_saver_cli \
    -f "$OUTPUT_DIR/$MAP_NAME" \
    --ros-args -p use_sim_time:=true

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
printf "║  ✅  Map saved:                                              ║\n"
printf "║     %-56s║\n" "$OUTPUT_DIR/$MAP_NAME.pgm"
printf "║     %-56s║\n" "$OUTPUT_DIR/$MAP_NAME.yaml"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [[ "$STAGE" == "5" || -n "$ENV_NAME" ]]; then
    echo "  Next step — launch navigation on this map:"
    echo "    ./start.sh navigate $MAP_NAME"
    echo ""
fi

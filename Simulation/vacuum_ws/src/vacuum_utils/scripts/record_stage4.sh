#!/usr/bin/env bash
# record_stage4.sh  —  Stage 4A: Rosbag Recording
# ─────────────────────────────────────────────────────────────
# Records all SLAM-relevant topics to a timestamped rosbag.
#
# Usage:
#   # Record in current terminal (Ctrl+C to stop):
#   bash src/vacuum_utils/scripts/record_stage4.sh room
#
#   # Record for a fixed duration (seconds):
#   bash src/vacuum_utils/scripts/record_stage4.sh office 300
#
#   # Replay a recorded bag for RTAB-Map post-processing:
#   ros2 bag play bags/stage4_manual_mapping/office/<bagname>.db3
#
# Topics recorded:
#   Camera:
#     /camera/color/image_raw
#     /camera/color/camera_info
#     /camera/depth/image_rect_raw
#     /camera/depth/camera_info
#     /camera/depth/points
#   Navigation:
#     /odom
#     /tf
#     /tf_static
#     /joint_states
#     /cmd_vel
#   RTAB-Map:
#     /rtabmap/map
#     /rtabmap/cloud_map
#     /rtabmap/odom
#     /rtabmap/info
#     /rtabmap/mapData
#     /rtabmap/mapGraph
#   Diagnostics:
#     /camera/diagnostics
#     /diagnostics
#   Clock:
#     /clock
# ─────────────────────────────────────────────────────────────

set -euo pipefail

ENVIRONMENT="${1:-room}"
DURATION="${2:-0}"   # 0 = record until Ctrl+C

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="bags/stage4_manual_mapping/${ENVIRONMENT}"
BAG_NAME="slam_${ENVIRONMENT}_${TIMESTAMP}"

mkdir -p "${OUTPUT_DIR}"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Stage 4A Rosbag Recording"
echo "════════════════════════════════════════════════════════"
echo "  Environment : ${ENVIRONMENT}"
echo "  Output dir  : ${OUTPUT_DIR}/${BAG_NAME}"
if [[ "${DURATION}" -gt 0 ]]; then
    echo "  Duration    : ${DURATION}s"
else
    echo "  Duration    : unlimited (Ctrl+C to stop)"
fi
echo "════════════════════════════════════════════════════════"
echo ""

# Source ROS2 if needed
if ! command -v ros2 &>/dev/null; then
    source /opt/ros/jazzy/setup.bash
fi
if [[ -f "install/setup.bash" ]]; then
    source install/setup.bash
fi

TOPICS=(
    # Camera pipeline
    "/camera/color/image_raw"
    "/camera/color/camera_info"
    "/camera/depth/image_rect_raw"
    "/camera/depth/camera_info"
    "/camera/depth/points"

    # Robot state
    "/odom"
    "/tf"
    "/tf_static"
    "/joint_states"
    "/cmd_vel"
    "/robot_description"

    # RTAB-Map outputs
    "/rtabmap/map"
    "/rtabmap/cloud_map"
    "/rtabmap/odom"
    "/rtabmap/info"
    "/rtabmap/mapData"
    "/rtabmap/mapGraph"

    # Diagnostics
    "/camera/diagnostics"
    "/diagnostics"

    # Clock (required for time-sync on replay)
    "/clock"
)

TOPIC_ARGS=()
for t in "${TOPICS[@]}"; do
    TOPIC_ARGS+=("-e" "$t")
done

CMD=(ros2 bag record
    --output "${OUTPUT_DIR}/${BAG_NAME}"
    --storage sqlite3
    --compression-mode file
    --compression-format zstd
    "${TOPIC_ARGS[@]}"
)

# Add duration limit if specified
if [[ "${DURATION}" -gt 0 ]]; then
    CMD+=(--duration "${DURATION}")
fi

echo "Topics to record: ${#TOPICS[@]}"
echo ""
echo "Starting recording... (Ctrl+C to stop)"
echo ""

"${CMD[@]}"

echo ""
echo "[ok] Recording complete."
echo "     Bag: ${OUTPUT_DIR}/${BAG_NAME}"
echo ""
echo "To replay:"
echo "  ros2 bag play ${OUTPUT_DIR}/${BAG_NAME} --clock"
echo ""
echo "To evaluate trajectory:"
echo "  python3.12 src/vacuum_utils/scripts/evaluate_trajectory.py \\"
echo "      --bag ${OUTPUT_DIR}/${BAG_NAME} \\"
echo "      --environment ${ENVIRONMENT}"

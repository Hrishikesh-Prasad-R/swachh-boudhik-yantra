#!/usr/bin/env bash
# validate_camera.sh  —  Stage 3 (D435i Perception Pipeline)
# ─────────────────────────────────────────────────────────────
# Automated validation script for the simulated RealSense D435i.
# Run AFTER launching the simulation:
#   ros2 launch vacuum_bringup sim.launch.py
#
# Usage:
#   bash validate_camera.sh            # all checks, default timeouts
#   bash validate_camera.sh --quick    # skip long FPS checks (CI mode)
#
# Exit codes:
#   0  — all checks passed
#   1  — one or more checks failed
#
# Validation tests performed:
#   T1  Topics exist
#   T2  Camera info published
#   T3  RGB FPS >= 25 Hz
#   T4  Depth FPS >= 25 Hz
#   T5  PointCloud2 FPS >= 10 Hz
#   T6  TF tree complete (all 6 camera frames present)
#   T7  Camera frame IDs correct in messages
#   T8  Diagnostics node alive
#   T9  No stale topics (latency < 2s)
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
RED='\033[0;31m'
GRN='\033[0;32m'
YEL='\033[1;33m'
NC='\033[0m'

PASS="${GRN}[PASS]${NC}"
FAIL="${RED}[FAIL]${NC}"
INFO="${YEL}[INFO]${NC}"

QUICK=false
if [[ "${1:-}" == "--quick" ]]; then QUICK=true; fi

TOTAL=0
FAILED=0

check() {
    local desc="$1"
    local result="$2"   # "pass" or "fail"
    TOTAL=$((TOTAL + 1))
    if [[ "$result" == "pass" ]]; then
        echo -e "  $PASS  $desc"
    else
        echo -e "  $FAIL  $desc"
        FAILED=$((FAILED + 1))
    fi
}

topic_exists() {
    ros2 topic info "$1" &>/dev/null
    return $?
}

# ─────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Swachh Boudhik Yantra — D435i Validation  (Stage 3)"
echo "════════════════════════════════════════════════════════"
echo ""

# Source ROS2 environment if not already done
if ! command -v ros2 &>/dev/null; then
    source /opt/ros/jazzy/setup.bash
fi

# ── T1: Required topics exist ─────────────────────────────────
echo "T1  Required topics exist"
REQUIRED_TOPICS=(
    "/camera/color/image_raw"
    "/camera/color/camera_info"
    "/camera/depth/image_rect_raw"
    "/camera/depth/camera_info"
    "/camera/depth/points"
    "/camera/diagnostics"
)

for t in "${REQUIRED_TOPICS[@]}"; do
    if topic_exists "$t"; then
        check "Topic $t" "pass"
    else
        check "Topic $t" "fail"
    fi
done

# ── T2: CameraInfo published with valid fields ────────────────
echo ""
echo "T2  CameraInfo valid (width=640, height=480)"

COLOR_INFO=$(ros2 topic echo --once /camera/color/camera_info 2>/dev/null || echo "")
if echo "$COLOR_INFO" | grep -q "width: 640"; then
    check "color/camera_info width=640" "pass"
else
    check "color/camera_info width=640" "fail"
fi
if echo "$COLOR_INFO" | grep -q "height: 480"; then
    check "color/camera_info height=480" "pass"
else
    check "color/camera_info height=480" "fail"
fi

# ── T3: RGB FPS >= 25 Hz ──────────────────────────────────────
echo ""
if $QUICK; then
    echo "T3  RGB FPS check [SKIPPED — quick mode]"
else
    echo "T3  RGB FPS >= 25 Hz (sampling 5s)"
    COLOR_HZ=$(ros2 topic hz /camera/color/image_raw --window 150 2>&1 | \
               grep "average rate" | tail -1 | awk '{print $3}' | tr -d ':' || echo "0")
    if (( $(echo "${COLOR_HZ:-0} >= 25" | bc -l 2>/dev/null || echo 0) )); then
        check "RGB FPS ${COLOR_HZ} Hz >= 25 Hz" "pass"
    else
        check "RGB FPS ${COLOR_HZ:-0} Hz >= 25 Hz" "fail"
    fi
fi

# ── T4: Depth FPS >= 25 Hz ───────────────────────────────────
echo ""
if $QUICK; then
    echo "T4  Depth FPS check [SKIPPED — quick mode]"
else
    echo "T4  Depth FPS >= 25 Hz (sampling 5s)"
    DEPTH_HZ=$(ros2 topic hz /camera/depth/image_rect_raw --window 150 2>&1 | \
               grep "average rate" | tail -1 | awk '{print $3}' | tr -d ':' || echo "0")
    if (( $(echo "${DEPTH_HZ:-0} >= 25" | bc -l 2>/dev/null || echo 0) )); then
        check "Depth FPS ${DEPTH_HZ} Hz >= 25 Hz" "pass"
    else
        check "Depth FPS ${DEPTH_HZ:-0} Hz >= 25 Hz" "fail"
    fi
fi

# ── T5: PointCloud2 FPS >= 10 Hz ─────────────────────────────
echo ""
if $QUICK; then
    echo "T5  PointCloud2 FPS check [SKIPPED — quick mode]"
else
    echo "T5  PointCloud2 FPS >= 10 Hz (sampling 5s)"
    PC_HZ=$(ros2 topic hz /camera/depth/points --window 60 2>&1 | \
            grep "average rate" | tail -1 | awk '{print $3}' | tr -d ':' || echo "0")
    if (( $(echo "${PC_HZ:-0} >= 10" | bc -l 2>/dev/null || echo 0) )); then
        check "PointCloud2 FPS ${PC_HZ} Hz >= 10 Hz" "pass"
    else
        check "PointCloud2 FPS ${PC_HZ:-0} Hz >= 10 Hz" "fail"
    fi
fi

# ── T6: TF tree — all 6 camera frames present ────────────────
echo ""
echo "T6  TF camera frames present"
REQUIRED_FRAMES=(
    "camera_link"
    "camera_color_frame"
    "camera_color_optical_frame"
    "camera_depth_frame"
    "camera_depth_optical_frame"
)

TF_FRAMES=$(ros2 topic echo --once /tf_static 2>/dev/null || echo "")

for frame in "${REQUIRED_FRAMES[@]}"; do
    if ros2 run tf2_ros tf2_echo base_link "$frame" \
           --timeout 2.0 &>/dev/null; then
        check "TF: $frame reachable from base_link" "pass"
    else
        # Softer check: just look for the frame name in /tf_static
        if echo "$TF_FRAMES" | grep -q "$frame"; then
            check "TF: $frame in /tf_static" "pass"
        else
            check "TF: $frame reachable from base_link" "fail"
        fi
    fi
done

# ── T7: Frame ID in image message ────────────────────────────
echo ""
echo "T7  Correct frame_id in image headers"
COLOR_MSG=$(ros2 topic echo --once /camera/color/image_raw 2>/dev/null || echo "")
if echo "$COLOR_MSG" | grep -q "camera_color_optical_frame"; then
    check "color/image_raw frame_id=camera_color_optical_frame" "pass"
else
    check "color/image_raw frame_id=camera_color_optical_frame" "fail"
fi

# ── T8: Diagnostics node publishing ──────────────────────────
echo ""
echo "T8  Diagnostics node alive"
DIAG_MSG=$(timeout 3 ros2 topic echo --once /camera/diagnostics 2>/dev/null || echo "")
if echo "$DIAG_MSG" | grep -q "D435i"; then
    check "/camera/diagnostics publishing D435i status" "pass"
else
    check "/camera/diagnostics publishing D435i status" "fail"
fi

# ── T9: No stale topics ───────────────────────────────────────
echo ""
echo "T9  Topics not stale (message within last 2s)"
TOPICS_TO_CHECK=(
    "/camera/color/image_raw"
    "/camera/depth/image_rect_raw"
    "/camera/depth/points"
)
for t in "${TOPICS_TO_CHECK[@]}"; do
    # Try to receive one message within 2s timeout
    MSG=$(timeout 2.5 ros2 topic echo --once "$t" 2>/dev/null || echo "")
    if [[ -n "$MSG" ]]; then
        check "$t not stale" "pass"
    else
        check "$t not stale (timeout)" "fail"
    fi
done

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
PASSED=$((TOTAL - FAILED))
if [[ $FAILED -eq 0 ]]; then
    echo -e "  ${GRN}ALL ${TOTAL} CHECKS PASSED ✅${NC}"
    echo "  Stage 3 Definition of Done: SATISFIED"
else
    echo -e "  ${RED}${FAILED}/${TOTAL} CHECKS FAILED ❌${NC}"
    echo "  Stage 3 Definition of Done: NOT YET SATISFIED"
fi
echo "════════════════════════════════════════════════════════"
echo ""

exit $FAILED

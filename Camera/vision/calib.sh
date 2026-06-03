#!/bin/bash
# Stereo Calibration Launcher — Jetson Orin Nano (Dual C270)
# Usage: ./calib.sh

source /opt/ros/humble/setup.bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ══════════════════════════════════════════════════════
# Step 0: Clean up
# ══════════════════════════════════════════════════════
echo "Cleaning up stale processes..."
pkill -9 -f usb_cam 2>/dev/null
pkill -9 -f cameracalibrator 2>/dev/null
pkill -9 -f stereo_matcher 2>/dev/null
rm -f /tmp/left_cam_fifo /tmp/right_cam_fifo /tmp/calib_fifo
sleep 1

# ══════════════════════════════════════════════════════
# Step 1: Detect cameras
# ══════════════════════════════════════════════════════
LEFT_DEV=""
RIGHT_DEV=""
for dev in /dev/video*; do
  [ -e "$dev" ] || continue
  v4l2-ctl -d "$dev" --list-formats | grep -E -q "YUYV|MJPG" || continue
  if [ -z "$LEFT_DEV" ]; then LEFT_DEV="$dev"
  elif [ -z "$RIGHT_DEV" ]; then RIGHT_DEV="$dev"; fi
done

if [ -z "$LEFT_DEV" ] || [ -z "$RIGHT_DEV" ]; then
  echo "ERROR: Could not find both cameras!"
  exit 1
fi

echo "  LEFT: $LEFT_DEV, RIGHT: $RIGHT_DEV"

# ══════════════════════════════════════════════════════
# Step 2: Pre-configure
# ══════════════════════════════════════════════════════
for DEV in $LEFT_DEV $RIGHT_DEV; do
  v4l2-ctl -d $DEV --set-ctrl=auto_exposure=1 --set-ctrl=exposure_time_absolute=151 \
    --set-ctrl=brightness=108 --set-ctrl=gain=34 --set-ctrl=white_balance_automatic=0 --set-ctrl=power_line_frequency=1
done

# Managed launch with FIFO + Terminal + Optional Log
launch_dual() {
    local label=$1
    local title=$2
    local fifo=$3
    local log=$4
    shift 4
    mkfifo "$fifo"
    gnome-terminal --title="$title" -- bash -c "cat $fifo; exec bash" 2>/dev/null &
    if [ -n "$log" ]; then
      "$@" 2>&1 | tee "$fifo" "$log" | sed "s/^/[$label] /" &
    else
      "$@" 2>&1 | tee "$fifo" | sed "s/^/[$label] /" &
    fi
}

# ══════════════════════════════════════════════════════
# Step 3: Launch LEFT camera (10 FPS for stability)
# ══════════════════════════════════════════════════════
echo "Starting LEFT camera..."
launch_dual "LEFT" "LEFT CAMERA" "/tmp/left_cam_fifo" "" \
  ros2 run usb_cam usb_cam_node_exe --ros-args \
  -p video_device:=$LEFT_DEV -p camera_name:=left_camera \
  -p image_width:=640 -p image_height:=480 \
  -p pixel_format:=mjpeg2rgb -p io_method:=mmap \
  -p framerate:=10.0 -r __ns:=/left_camera

# Wait for LEFT
for i in $(seq 1 10); do
  sleep 1
  if ros2 topic list 2>/dev/null | grep -q "/left_camera/image_raw"; then
    echo "  ✓ LEFT camera topic live!"
    break
  fi
  [ $i -eq 10 ] && echo "  ✗ LEFT camera topic timeout!" && exit 1
done

# ══════════════════════════════════════════════════════
# Step 4: Launch RIGHT camera (10 FPS for stability)
# ══════════════════════════════════════════════════════
echo "Starting RIGHT camera..."
launch_dual "RIGHT" "RIGHT CAMERA" "/tmp/right_cam_fifo" "" \
  ros2 run usb_cam usb_cam_node_exe --ros-args \
  -p video_device:=$RIGHT_DEV -p camera_name:=right_camera \
  -p image_width:=640 -p image_height:=480 \
  -p pixel_format:=mjpeg2rgb -p io_method:=mmap \
  -p framerate:=10.0 -r __ns:=/right_camera

# Wait for RIGHT
for i in $(seq 1 10); do
  sleep 1
  if ros2 topic list 2>/dev/null | grep -q "/right_camera/image_raw"; then
    echo "  ✓ RIGHT camera topic live!"
    break
  fi
  [ $i -eq 10 ] && echo "  ✗ RIGHT camera topic timeout!" && exit 1
done

# ══════════════════════════════════════════════════════
# Step 4.5: Verify DATA FLOW (Actual frames check)
# ══════════════════════════════════════════════════════
echo ""
echo "Verifying data flow (checking for actual frames)..."
for TOPIC in "/left_camera/image_raw" "/right_camera/image_raw"; do
  if timeout 5s ros2 topic echo --once $TOPIC >/dev/null 2>&1; then
    echo "  ✓ $TOPIC is streaming!"
  else
    echo "  ✗ $TOPIC is NOT streaming data! (Check USB bandwidth/cables)"
    exit 1
  fi
done

# Re-apply settings
for DEV in $LEFT_DEV $RIGHT_DEV; do
  v4l2-ctl -d $DEV --set-ctrl=white_balance_automatic=0 --set-ctrl=auto_exposure=1 \
    --set-ctrl=exposure_time_absolute=151 --set-ctrl=brightness=108 --set-ctrl=gain=34
done

# ══════════════════════════════════════════════════════
# Step 5: Launch Calibrator
# ══════════════════════════════════════════════════════
echo "Launching calibrator..."
CALIB_LOG="/tmp/calib_stdout.log"
rm -f "$CALIB_LOG"

launch_dual "CALIB" "STEREO CALIBRATOR" "/tmp/calib_fifo" "$CALIB_LOG" \
  ros2 run camera_calibration cameracalibrator \
  --approximate 0.1 --size 7x5 --square 0.034 --ros-args \
  -r left:=/left_camera/image_raw -r right:=/right_camera/image_raw \
  -r left_camera:=/left_camera -r right_camera:=/right_camera

echo "════════════════════════════════════════════════"
echo "  STRATEGY TO FIX EPI Error:"
echo "  1. HOLD BOARD STEADY for 0.5s at each position."
echo "  2. DO NOT MOVE it while the purple/green bars fill."
echo "  3. Aim for 30-40 steady samples, then hit CALIBRATE."
echo "════════════════════════════════════════════════"
read -rp "  Press ENTER after you've clicked SAVE in the calibrator... "

# ══════════════════════════════════════════════════════
# Step 6: Export
# ══════════════════════════════════════════════════════
TARBALL="/tmp/calibrationdata.tar.gz"
NPZ_OUT="$SCRIPT_DIR/calib/stereo_calib.npz"

# Try to extract EPI from log
EPI=$(grep -a "epi =" "$CALIB_LOG" 2>/dev/null | tail -n 1 | awk '{print $NF}')
[ -z "$EPI" ] && [ -f "$CALIB_LOG" ] && EPI=$(grep -a "epi" "$CALIB_LOG" | tail -n 1 | awk '{print $NF}')
[ -z "$EPI" ] && EPI="Unknown (Check pop-up window)"

if [ ! -f "$TARBALL" ]; then
  echo "  ✗ ERROR: $TARBALL not found! Did you click SAVE?"
  exit 1
fi

mkdir -p "$SCRIPT_DIR/calib"
python3 "$SCRIPT_DIR/save_calib.py" --tarball "$TARBALL" --out "$NPZ_OUT"

echo ""
echo "════════════════════════════════════════════════"
echo "           CALIBRATION QUALITY REPORT           "
echo "════════════════════════════════════════════════"
echo "  RMS Epipolar Error (EPI): $EPI"

# Check for abnormal values in the generated YAML
if grep -q "cx0: -" "$SCRIPT_DIR/calib/calibration_values.yaml"; then
  echo "  ⚠️  WARNING: Negative 'cx0' detected!"
  echo "      Your cameras are likely pointing AWAY from each other."
elif grep -E -q "cx0: [7-9][0-9][0-9]" "$SCRIPT_DIR/calib/calibration_values.yaml"; then
  echo "  ⚠️  WARNING: Out-of-bounds 'cx0' (>640) detected!"
  echo "      Your cameras are likely pointing TOWARDS each other."
fi

if (( $(echo "$EPI < 0.5" | bc -l 2>/dev/null || echo 0) )); then
  echo "  ✅ EXCELLENT: Error is below 0.5. Robot is ready!"
elif (( $(echo "$EPI < 1.4" | bc -l 2>/dev/null || echo 0) )); then
  echo "  ⚠️  MODERATE: Accuracy may be slightly off. (Target < 0.5)"
else
  echo "  ❌ POOR: Error is too high ($EPI). Recalibrate for depth accuracy."
fi
echo "════════════════════════════════════════════════"

pkill -9 -f usb_cam
pkill -9 -f cameracalibrator
rm -f /tmp/left_cam_fifo /tmp/right_cam_fifo /tmp/calib_fifo "$CALIB_LOG"

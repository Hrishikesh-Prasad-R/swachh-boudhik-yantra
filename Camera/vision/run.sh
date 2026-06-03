#!/usr/bin/env bash
# run.sh — Swachh MVP Launcher
# Applies camera settings and starts the detection pipeline.
# Usage: ./run.sh [--color]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Parse args ────────────────────────────────────────────────────────────────
EXTRA_ARGS=""
for arg in "$@"; do
  if [ "$arg" == "--color" ]; then
    EXTRA_ARGS="--color"
  fi
done

echo ""
echo "════════════════════════════════════════════════"
echo "   Swachh Boudhik Yantra — MVP"
echo "════════════════════════════════════════════════"
echo ""

# ── Auto-detect both C270 cameras ────────────────────────────────────────────
LEFT_DEV=""
RIGHT_DEV=""

for dev in /dev/video*; do
  [ -e "$dev" ] || continue
  v4l2-ctl -d "$dev" --list-formats 2>/dev/null | grep -E -q "YUYV|MJPG" || continue
  if [ -z "$LEFT_DEV" ]; then
    LEFT_DEV="$dev"
  elif [ -z "$RIGHT_DEV" ]; then
    RIGHT_DEV="$dev"
  fi
done

if [ -z "$LEFT_DEV" ] || [ -z "$RIGHT_DEV" ]; then
  echo "ERROR: Could not detect both cameras!"
  echo "  LEFT:  ${LEFT_DEV:-NOT FOUND}"
  echo "  RIGHT: ${RIGHT_DEV:-NOT FOUND}"
  exit 1
fi

echo "  LEFT  camera: $LEFT_DEV"
echo "  RIGHT camera: $RIGHT_DEV"
echo ""

# ── Apply v4l2 settings ───────────────────────────────────────────────────────
echo "Applying camera settings..."
for DEV in "$LEFT_DEV" "$RIGHT_DEV"; do
  v4l2-ctl -d "$DEV" --set-ctrl=auto_exposure=1 || true
  v4l2-ctl -d "$DEV" --set-ctrl=exposure_time_absolute=151 || true
  v4l2-ctl -d "$DEV" --set-ctrl=brightness=108 || true
  v4l2-ctl -d "$DEV" --set-ctrl=gain=34 || true
  v4l2-ctl -d "$DEV" --set-ctrl=white_balance_automatic=0 || true
  v4l2-ctl -d "$DEV" --set-ctrl=power_line_frequency=1 || true
done
echo "  ✓ Camera settings applied (skipped unsupported)."

# ── Check model ───────────────────────────────────────────────────────────────
MODEL="models/yolov8s.onnx"
if [ ! -f "$MODEL" ]; then
  echo ""
  echo "ERROR: Model not found at $MODEL"
  echo "Run ./setup.sh to download and prepare the model."
  echo ""
  exit 1
fi

# ── Check calib ───────────────────────────────────────────────────────────────
CALIB="calib/stereo_calib.npz"
if [ ! -f "$CALIB" ]; then
  echo ""
  echo "NOTE: Calibration file not found ($CALIB)"
  echo "  → Depth will use bounding-box fallback (metric values unavailable)"
  echo "  → Run stereo calibration and save output to $CALIB"
  echo ""
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "Launching pipeline... (q or ESC to quit)"
echo ""
./venv/bin/python3 main.py $EXTRA_ARGS

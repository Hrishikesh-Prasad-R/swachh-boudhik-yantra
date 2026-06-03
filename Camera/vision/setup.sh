#!/usr/bin/env bash
# setup.sh — One-time MVP setup
# Downloads YOLOv8s, exports to ONNX, converts to TensorRT FP16 engine.
# Run this ONCE before ./run.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "════════════════════════════════════════════════"
echo "   Swachh MVP — One-Time Setup"
echo "════════════════════════════════════════════════"
echo ""

# ── Step 1: Python deps ───────────────────────────────────────────────────────
echo "[1/3] Installing Python dependencies..."
pip install --quiet ultralytics pyyaml pyserial onnxruntime "numpy<2.0.0"
echo "  ✓ ultralytics, pyyaml, pyserial, onnxruntime, numpy<2.0.0 installed"

# ── Step 2: Download YOLOv8s and export to ONNX ──────────────────────────────
echo ""
echo "[2/3] Exporting YOLOv8s → ONNX..."
mkdir -p models

if [ -f "models/yolov8s.onnx" ]; then
  echo "  ✓ models/yolov8s.onnx already exists — skipping"
else
  python3 - <<'PYEOF'
from ultralytics import YOLO
import shutil, os

print("  Downloading yolov8s.pt and exporting to ONNX...")
model = YOLO("yolov8s.pt")
# Export to ONNX with fixed input shape 1x3x640x640
model.export(format="onnx", imgsz=640, simplify=True, opset=17, dynamic=False)
# Ultralytics saves to yolov8s.onnx in cwd
if os.path.isfile("yolov8s.onnx"):
    shutil.move("yolov8s.onnx", "models/yolov8s.onnx")
    print("  ✓ Saved: models/yolov8s.onnx")
else:
    print("  ERROR: yolov8s.onnx not found after export — check Ultralytics output dir")
PYEOF
fi

# ── Step 3: Verify ────────────────────────────────────────────────────────────
echo ""
echo "[3/3] Verifying..."
python3 - <<'PYEOF'
import os, sys
ok = True
checks = [
    ("models/yolov8s.onnx",   "ONNX model"),
    ("config.yaml",           "Config"),
]
for path, label in checks:
    if os.path.isfile(path):
        size = os.path.getsize(path) / (1024**2)
        print(f"  ✓ {label}: {path}  ({size:.1f} MB)")
    else:
        print(f"  ✗ MISSING {label}: {path}")
        ok = False

calib = "calib/stereo_calib.npz"
if os.path.isfile(calib):
    print(f"  ✓ Calibration: {calib}")
else:
    print(f"  ⚠  Calibration not found — run ./calib.sh then python3 save_calib.py")

if not ok:
    sys.exit(1)
PYEOF

echo ""
echo "════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Run stereo calibration:  ./calib.sh"
echo "     Then export:             python3 save_calib.py"
echo "  2. Start pipeline:          ./run.sh"
echo "════════════════════════════════════════════════"
echo ""

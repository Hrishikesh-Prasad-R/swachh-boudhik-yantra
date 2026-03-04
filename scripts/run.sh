#!/bin/bash
# ═══════════════════════════════════════════
#  Swachh Boudhik Yantra — One-Click Runner
# ═══════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$DIR/build"

echo "╔══════════════════════════════════════════╗"
echo "║   Swachh Boudhik Yantra — Starting...    ║"
echo "╚══════════════════════════════════════════╝"

# ── Step 1: Build if needed ──
if [ ! -f "$BUILD_DIR/swacch_hmi" ]; then
    echo "[BUILD] First run — compiling HMI..."
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"
    cmake .. && make -j$(nproc)
    if [ $? -ne 0 ]; then
        echo "[ERROR] Build failed!"
        exit 1
    fi
    echo "[BUILD] Done!"
else
    echo "[BUILD] Binary already exists, skipping build."
fi

# ── Step 2: Auto-detect Arduino serial port ──
PORT=""
for p in /dev/ttyUSB* /dev/ttyACM*; do
    if [ -e "$p" ]; then
        PORT="$p"
        break
    fi
done

if [ -z "$PORT" ]; then
    echo "[ERROR] No Arduino detected! Plug in the USB cable."
    echo "        Running without hardware..."
    PORT="/dev/ttyUSB0"
fi

echo "[PORT]  Using: $PORT"

# ── Step 3: Run HMI ──
echo "[RUN]   Launching HMI..."
echo ""
exec "$BUILD_DIR/swacch_hmi" --port "$PORT"

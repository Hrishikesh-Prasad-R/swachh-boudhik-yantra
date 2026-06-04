#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# sync_calib.sh — Sync stereo calibration file from RPi to GPU system
#
# Run on the RPi. Copies stereo_calib.npz to the GPU system over the hotspot.
#
# Usage:
#   bash sync_calib.sh <gpu_windows_ip>
#   bash sync_calib.sh 192.168.4.101          # typical GPU IP from DHCP
#
# Requirements (on GPU system):
#   - OpenSSH server must be enabled on Windows 11
#   - Enable via: Settings → System → Optional Features → OpenSSH Server
#   - Or via PowerShell (admin): Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

# ── Args ──────────────────────────────────────────────────────────────────────
GPU_IP="${1:-}"
if [[ -z "$GPU_IP" ]]; then
    echo "Usage: bash sync_calib.sh <gpu_windows_ip>"
    echo "Example: bash sync_calib.sh 192.168.4.101"
    echo ""
    echo "To find the GPU system's IP on the hotspot:"
    echo "  cat /var/lib/misc/dnsmasq.leases   (on RPi)"
    echo "  # or check WiFi settings on the Windows machine"
    exit 1
fi

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CALIB_FILE="$REPO_ROOT/Camera/vision/calib/stereo_calib.npz"
# Destination on Windows — adjust username as needed
GPU_USER="${GPU_USER:-$USER}"
GPU_DEST_DIR="Desktop/swachh-boudhik-yantra/Camera/vision/calib"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Swachh — Calibration File Sync (RPi → GPU)        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
info "Source: $CALIB_FILE"
info "Target: ${GPU_USER}@${GPU_IP}:~/${GPU_DEST_DIR}/"
echo ""

# ── Check source file ─────────────────────────────────────────────────────────
if [[ ! -f "$CALIB_FILE" ]]; then
    warn "Calibration file NOT found at: $CALIB_FILE"
    warn "Run stereo calibration first:"
    warn "  cd Camera/vision && bash calib.sh"
    echo ""
    warn "Alternatively, run gpu_worker.py with --no-depth flag:"
    warn "  python gpu_worker.py --no-depth"
    exit 0
fi

CALIB_SIZE=$(du -h "$CALIB_FILE" | cut -f1)
info "Calibration file found: $CALIB_SIZE"

# ── Ping check ────────────────────────────────────────────────────────────────
info "Checking connectivity to GPU system ($GPU_IP)..."
if ! ping -c 2 -W 2 "$GPU_IP" > /dev/null 2>&1; then
    fail "Cannot reach $GPU_IP. Is the GPU system connected to 'swachh-bot' hotspot?"
fi
info "GPU system reachable ✓"

# ── Create destination directory on Windows via SSH ──────────────────────────
info "Creating destination directory on Windows..."
ssh "${GPU_USER}@${GPU_IP}" \
    "mkdir -p \"\$USERPROFILE\\${GPU_DEST_DIR//\//\\\\}\"" 2>/dev/null || \
ssh "${GPU_USER}@${GPU_IP}" \
    "cmd /c mkdir \"%USERPROFILE%\\${GPU_DEST_DIR//\//\\\\}\" 2>nul || exit 0"

# ── SCP transfer ──────────────────────────────────────────────────────────────
info "Transferring calibration file..."
scp -v "$CALIB_FILE" \
    "${GPU_USER}@${GPU_IP}:${GPU_DEST_DIR}/stereo_calib.npz"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Calibration sync complete! ✓                      ║"
echo "║                                                      ║"
echo "║   File is now at (on Windows):                      ║"
echo "║   %USERPROFILE%\\$GPU_DEST_DIR  ║"
echo "║                                                      ║"
echo "║   Run gpu_worker.py WITHOUT --no-depth flag now.    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

info "To re-sync after re-calibrating:"
info "  bash sync_calib.sh $GPU_IP"

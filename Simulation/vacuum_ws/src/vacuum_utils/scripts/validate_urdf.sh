#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# validate_urdf.sh
# ─────────────────────────────────────────────────────────────────────────────
# Automated URDF validation for Stage 1.
#
# Tests performed:
#   1. Xacro expansion: confirms no Xacro syntax errors
#   2. URDF schema validation: check_urdf confirms link/joint structure
#   3. Reports all links and joints found
#
# Usage:
#   bash validate_urdf.sh
#   bash validate_urdf.sh /path/to/custom.urdf.xacro
#
# Exit codes:
#   0 — all tests passed
#   1 — Xacro expansion failed
#   2 — URDF validation failed
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Setup ──────────────────────────────────────────────────────────────────
source /opt/ros/jazzy/setup.bash

# Find the workspace install directory (walk up from script location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_ROOT="$(realpath "${SCRIPT_DIR}/../../../..")"
INSTALL="${WS_ROOT}/install"

if [[ -f "${INSTALL}/setup.bash" ]]; then
  source "${INSTALL}/setup.bash"
else
  echo "[WARN] Workspace not built yet. Run 'colcon build' first."
  echo "       Attempting to find URDF via source tree..."
  XACRO_FILE="${WS_ROOT}/src/vacuum_description/urdf/vacuum.urdf.xacro"
fi

# ── Locate URDF file ───────────────────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
  XACRO_FILE="$1"
elif [[ -z "${XACRO_FILE:-}" ]]; then
  # Find via installed share directory
  PKG_SHARE="$(ros2 pkg prefix vacuum_description 2>/dev/null)/share/vacuum_description"
  XACRO_FILE="${PKG_SHARE}/urdf/vacuum.urdf.xacro"
fi

if [[ ! -f "${XACRO_FILE}" ]]; then
  echo "[ERROR] Xacro file not found: ${XACRO_FILE}"
  echo "        Build the workspace first: cd ${WS_ROOT} && colcon build"
  exit 1
fi

TMPDIR=$(mktemp -d)
URDF_OUT="${TMPDIR}/vacuum_robot.urdf"

echo "═══════════════════════════════════════════════════════════"
echo "  Vacuum Robot — URDF Validation"
echo "  Source: ${XACRO_FILE}"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Xacro expansion ────────────────────────────────────────────────
echo "[1/3] Expanding Xacro → URDF..."
if xacro "${XACRO_FILE}" -o "${URDF_OUT}" 2>&1; then
  echo "      ✅ Xacro expansion succeeded"
  echo "      Output: ${URDF_OUT}"
  echo "      Size: $(wc -c < "${URDF_OUT}") bytes"
else
  echo "      ❌ Xacro expansion FAILED"
  exit 1
fi
echo ""

# ── Step 2: URDF structural validation ─────────────────────────────────────
echo "[2/3] Running check_urdf..."
if check_urdf "${URDF_OUT}" 2>&1; then
  echo "      ✅ URDF structure valid"
else
  echo "      ❌ URDF validation FAILED"
  cat "${URDF_OUT}"
  exit 2
fi
echo ""

# ── Step 3: Count and list elements ────────────────────────────────────────
echo "[3/3] Robot model summary:"
LINK_COUNT=$(grep -c "<link " "${URDF_OUT}" || true)
JOINT_COUNT=$(grep -c "<joint " "${URDF_OUT}" || true)
echo "      Links:  ${LINK_COUNT}"
echo "      Joints: ${JOINT_COUNT}"
echo ""
echo "      Link names:"
grep -oP 'name="\K[^"]+' "${URDF_OUT}" | grep -v "^vacuum_robot$" | head -20 | \
  while read -r name; do echo "        - ${name}"; done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ ALL VALIDATION TESTS PASSED"
echo "═══════════════════════════════════════════════════════════"

# Clean up
rm -rf "${TMPDIR}"

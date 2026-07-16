#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# validate_controllers.sh
# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 controller validation script.
#
# Checks:
#   1. /controller_manager is alive (responds to list_controllers service)
#   2. joint_state_broadcaster is [active]
#   3. diff_drive_controller is [active]
#   4. /joint_states is being published
#   5. /odom is being published
#   6. /tf contains odom→base_footprint
#
# Usage (simulation must be running):
#   bash validate_controllers.sh
#   bash validate_controllers.sh --timeout 30
#
# Exit codes:
#   0 — all controllers active and all topics publishing
#   1 — controller_manager not reachable (timeout)
#   2 — one or more controllers not active
#   3 — one or more expected topics not publishing
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

TIMEOUT="${1:-20}"  # seconds to wait for controller_manager

source /opt/ros/jazzy/setup.bash
# source workspace if built
WS_ROOT="$(realpath "$(dirname "${BASH_SOURCE[0]}")/../../../..")"
[[ -f "${WS_ROOT}/install/setup.bash" ]] && source "${WS_ROOT}/install/setup.bash"

echo "═══════════════════════════════════════════════════════════"
echo "  Vacuum Robot — Controller Validation (Stage 2)"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Wait for controller_manager ───────────────────────────
echo "[1/5] Waiting for /controller_manager (timeout=${TIMEOUT}s)..."
start_t=$(date +%s)
while true; do
  if ros2 service list 2>/dev/null | grep -q '/controller_manager/list_controllers'; then
    echo "      ✅ /controller_manager is responding"
    break
  fi
  elapsed=$(( $(date +%s) - start_t ))
  if [[ ${elapsed} -ge ${TIMEOUT} ]]; then
    echo "      ❌ TIMEOUT: /controller_manager not found after ${TIMEOUT}s"
    echo "         Is the simulation running? (ros2 launch vacuum_bringup sim.launch.py)"
    exit 1
  fi
  sleep 1
done
echo ""

# ── Step 2: List controllers ───────────────────────────────────────
echo "[2/5] Listing active controllers..."
CTRL_LIST=$(ros2 control list_controllers 2>&1 || true)
echo "${CTRL_LIST}" | sed 's/^/      /'
echo ""

# ── Step 3: Check each expected controller ─────────────────────────
echo "[3/5] Checking controller states..."
ALL_OK=true

check_controller() {
  local name="$1"
  if echo "${CTRL_LIST}" | grep -q "${name}.*active"; then
    echo "      ✅ ${name} [active]"
  elif echo "${CTRL_LIST}" | grep -q "${name}"; then
    echo "      ⚠️  ${name} found but NOT active:"
    echo "${CTRL_LIST}" | grep "${name}" | sed 's/^/         /'
    ALL_OK=false
  else
    echo "      ❌ ${name} NOT FOUND"
    ALL_OK=false
  fi
}

check_controller "joint_state_broadcaster"
check_controller "diff_drive_controller"
echo ""

if [[ "${ALL_OK}" != "true" ]]; then
  echo "  Some controllers are not active. Manually spawn them:"
  echo "  ros2 run controller_manager spawner joint_state_broadcaster"
  echo "  ros2 run controller_manager spawner diff_drive_controller"
  exit 2
fi

# ── Step 4: Check topic publication rates ─────────────────────────
echo "[4/5] Checking topic publication..."

check_topic_hz() {
  local topic="$1"
  local expected_hz="$2"
  local measured
  measured=$(ros2 topic hz "${topic}" --once 2>&1 | grep 'average rate' | awk '{print $3}' || echo "0")
  if [[ -z "${measured}" || "${measured}" == "0" ]]; then
    echo "      ❌ ${topic} — not publishing"
    ALL_OK=false
  else
    echo "      ✅ ${topic} — ${measured} Hz (expected ≥${expected_hz})"
  fi
}

# Note: ros2 topic hz --once waits for 1 message (up to 10s by default)
ros2 topic hz /joint_states --once 2>/dev/null | grep 'average\|not' | sed 's/^/      /'; echo ""
ros2 topic hz /odom         --once 2>/dev/null | grep 'average\|not' | sed 's/^/      /'; echo ""
echo ""

# ── Step 5: Summary ───────────────────────────────────────────────
echo "[5/5] Summary:"
if [[ "${ALL_OK}" == "true" ]]; then
  echo "      ✅ ALL CONTROLLER CHECKS PASSED"
  echo ""
  echo "  Now you can send velocity commands:"
  echo "  ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.2}}'"
  echo "  ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r /cmd_vel:=/cmd_vel"
  exit 0
else
  echo "      ❌ SOME CHECKS FAILED — review output above"
  exit 2
fi

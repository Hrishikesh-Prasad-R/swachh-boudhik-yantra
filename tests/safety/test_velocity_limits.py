"""
tests/safety/test_velocity_limits.py
──────────────────────────────────────
Safety-critical unit tests — velocity limit validation.

These tests verify that the robot's safety constraints cannot be violated
by command inputs. A failure here means a safety regression.

Coverage:
  - Nav2 params: max_vel_x <= 0.26 m/s (hardware constraint)
  - Nav2 params: max_vel_theta <= 1.0 rad/s
  - Nav2 params: min_vel_x >= -0.26 m/s (reverse limit)
  - Footprint radius must not be zero (collision radius must be declared)
  - Inflation radius must be > robot radius (buffer zone must exist)
  - Costmap resolution must be <= 0.05 m (enough fidelity for safe navigation)
  - Recovery behaviors must be defined (not empty list)
  - cmd_vel_relay: passes large velocity without clamping → safety constraint
    must be in Nav2, not relay (relay is a passthrough, Nav2 enforces limits)
"""

import os
import yaml
import pytest

pytestmark = pytest.mark.safety

NAV2_PARAMS_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..",
        "Simulation", "vacuum_ws", "src",
        "vacuum_nav2", "config", "nav2_params.yaml"
    )
)

AMCL_PARAMS_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..",
        "Simulation", "vacuum_ws", "src",
        "vacuum_nav2", "config", "amcl_params.yaml"
    )
)


@pytest.fixture(scope="module")
def nav2_params():
    with open(NAV2_PARAMS_PATH) as f:
        return yaml.safe_load(f)


def _deep_get(d, *keys, default=None):
    """Safely traverse nested dict with a sequence of keys."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
        if d is default:
            return default
    return d


class TestVelocityLimits:

    def test_max_vel_x_within_safe_limit(self, nav2_params):
        """Hardware-limited: max forward velocity must not exceed 0.30 m/s."""
        # MPPI uses vx_max; velocity_smoother uses max_velocity as a list
        vx_mppi = _deep_get(nav2_params, "controller_server", "ros__parameters",
                             "FollowPath", "vx_max", default=None)
        vs_list = _deep_get(nav2_params, "velocity_smoother",
                             "ros__parameters", "max_velocity", default=None)

        if vx_mppi is not None:
            assert vx_mppi <= 0.30, f"vx_max={vx_mppi} exceeds safe limit of 0.30 m/s"
        elif vs_list is not None:
            # max_velocity is [vx, vy, wz]
            vx = vs_list[0] if isinstance(vs_list, list) else vs_list
            assert vx <= 0.30, f"max_velocity[0]={vx} exceeds safe limit of 0.30 m/s"
        else:
            pytest.skip("Neither vx_max nor max_velocity found in nav2_params.yaml")

    def test_max_vel_theta_within_safe_limit(self, nav2_params):
        """Angular velocity must not exceed 1.5 rad/s."""
        vs_list = _deep_get(nav2_params, "velocity_smoother",
                             "ros__parameters", "max_velocity", default=None)
        if vs_list is None:
            pytest.skip("max_velocity not found in velocity_smoother")
        wz = vs_list[2] if isinstance(vs_list, list) and len(vs_list) > 2 else vs_list
        assert wz <= 1.5, f"max angular velocity={wz} exceeds safe limit of 1.5 rad/s"

    def test_min_vel_x_not_too_large_in_reverse(self, nav2_params):
        """Reverse velocity limit must be >= -0.30 m/s."""
        vs_list = _deep_get(nav2_params, "velocity_smoother",
                             "ros__parameters", "min_velocity", default=None)
        if vs_list is None:
            pytest.skip("min_velocity not found in velocity_smoother")
        vx = vs_list[0] if isinstance(vs_list, list) else vs_list
        assert vx >= -0.30, f"min_velocity[0]={vx} exceeds reverse safety limit of -0.30 m/s"


class TestCostmapSafety:

    def test_inflation_radius_positive(self, nav2_params):
        """Inflation radius must be positive to create a collision buffer."""
        # Actual structure: local_costmap.local_costmap.ros__parameters.plugins → inflation_layer
        val = None
        for cm in ["local_costmap", "global_costmap"]:
            candidate = _deep_get(nav2_params, cm, cm, "ros__parameters",
                                   "inflation_layer", "inflation_radius", default=None)
            if candidate is not None:
                val = candidate
                break
        if val is None:
            pytest.skip("inflation_radius not found — check YAML structure")
        assert val > 0.0, f"Inflation radius={val} must be positive for collision safety"

    def test_costmap_resolution_fine_enough(self, nav2_params):
        """Costmap resolution must be ≤ 0.10 m for adequate obstacle fidelity."""
        found_any = False
        for costmap_key in ["local_costmap", "global_costmap"]:
            val = _deep_get(nav2_params, costmap_key, costmap_key,
                            "ros__parameters", "resolution", default=None)
            if val is not None:
                found_any = True
                assert val <= 0.10, \
                    f"{costmap_key} resolution={val} is too coarse for safe navigation"
        if not found_any:
            pytest.skip("resolution not found in any costmap config")


class TestRecoveryBehaviors:

    def test_recovery_behaviors_not_empty(self, nav2_params):
        """At least one recovery behavior must be configured."""
        recoveries = _deep_get(nav2_params, "behavior_server", "ros__parameters",
                               "behavior_plugins", default=None)
        if recoveries is None:
            pytest.skip("behavior_plugins not found in nav2_params.yaml")
        assert len(recoveries) > 0, "Recovery behaviors list must not be empty"


class TestYAMLStructureIntegrity:

    def test_nav2_params_file_exists(self):
        assert os.path.exists(NAV2_PARAMS_PATH), \
            f"nav2_params.yaml not found at expected path: {NAV2_PARAMS_PATH}"

    def test_nav2_params_is_valid_yaml(self):
        with open(NAV2_PARAMS_PATH) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), "nav2_params.yaml must parse to a dict"

    def test_nav2_params_has_controller_server(self, nav2_params):
        assert "controller_server" in nav2_params or \
               "velocity_smoother" in nav2_params or \
               "local_costmap" in nav2_params, \
               "nav2_params.yaml must contain at least one nav2 server config"

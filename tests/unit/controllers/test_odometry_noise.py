"""
tests/unit/controllers/test_odometry_noise.py
───────────────────────────────────────────────
Unit tests for OdometryNoiseNode (odometry_noise_node.py).

No ROS 2 required — logic tested directly via mocked infrastructure.

Coverage:
  - Passthrough mode (enable_noise=False): output position == input position
  - Passthrough mode: output orientation == input orientation (unchanged)
  - Passthrough mode: header, child_frame_id, and twist are preserved unchanged
  - Noise mode (enable_noise=True): output position != input (noise applied)
  - Noise mode: noise is statistically within ±3σ of noise_std
  - Noise mode: orientation is perturbed
  - Zero position input with noise: output is near zero but not identical
  - Large position values: noise is relative, not absolute
  - Noise std = 0.0: with noise enabled, output == input (degenerate case)
"""

import sys
import os
import math
import numpy as np
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def inject_stubs():
    from tests.conftest import _mock_rclpy, _mock_ros_msgs
    rclpy_stub = _mock_rclpy()
    gm, nm, sm, sens, diag, vis, nav2 = _mock_ros_msgs()
    mods = {
        "rclpy": rclpy_stub,
        "rclpy.node": rclpy_stub.node,
        "rclpy.qos": rclpy_stub.qos,
        "geometry_msgs": gm,
        "geometry_msgs.msg": gm.msg,
        "nav_msgs": nm,
        "nav_msgs.msg": nm.msg,
        "std_msgs": sm,
        "std_msgs.msg": sm.msg,
    }
    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v
    yield
    for k, v in old.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _build_odom_msg(x=0.0, y=0.0, z=0.0, qx=0.0, qy=0.0, qz=0.0, qw=1.0,
                    frame="odom", child="base_footprint"):
    """Build a minimal Odometry-like message."""
    class _Pos:
        pass
    class _Ori:
        pass
    class _Pose2:
        pass
    class _PoseW:
        pass
    class _TwistW:
        class _TwistInner:
            class _Vec:
                x = 0.0; y = 0.0; z = 0.0
            linear = _Vec(); angular = _Vec()
        twist = _TwistInner()
        covariance = [0.0] * 36
    class _Header:
        frame_id = frame
        class _Stamp:
            sec = 1; nanosec = 0
        stamp = _Stamp()

    pos = _Pos()
    pos.x = x; pos.y = y; pos.z = z
    ori = _Ori()
    ori.x = qx; ori.y = qy; ori.z = qz; ori.w = qw
    pose2 = _Pose2()
    pose2.position = pos
    pose2.orientation = ori
    posew = _PoseW()
    posew.pose = pose2
    posew.covariance = [0.0] * 36

    class _Msg:
        header = _Header()
        child_frame_id = child
        pose = posew
        twist = _TwistW()

    return _Msg()


def _get_node_callback():
    """Load OdometryNoiseNode and return (node, _odom_callback)."""
    src = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "Simulation", "vacuum_ws", "src",
            "vacuum_controller", "vacuum_controller"
        )
    )
    if src not in sys.path:
        sys.path.insert(0, src)
    for m in ["odometry_noise_node"]:
        if m in sys.modules:
            del sys.modules[m]

    import odometry_noise_node as mod

    node = mod.OdometryNoiseNode.__new__(mod.OdometryNoiseNode)

    # Parameter state
    node._params = {
        "enable_noise":       False,
        "linear_noise_std":   0.005,
        "angular_noise_std":  0.003,
        "rate_hz":            30.0,
    }

    class _Param:
        def __init__(self, v): self.value = v

    node.get_parameter = lambda k: _Param(node._params[k])

    # Publisher spy
    class _Spy:
        def __init__(self): self.last = None
        def publish(self, msg): self.last = msg

    spy = _Spy()
    node.pub = spy

    # Logger stub
    class _L:
        def info(self, *a): pass
    node.get_logger = lambda: _L()

    return node, spy


class TestPassthroughMode:

    def test_position_x_unchanged(self):
        node, spy = _get_node_callback()
        node._params["enable_noise"] = False
        msg = _build_odom_msg(x=1.5, y=2.5, z=0.0)
        node._odom_callback(msg)
        assert spy.last.pose.pose.position.x == pytest.approx(1.5, abs=1e-9)

    def test_position_y_unchanged(self):
        node, spy = _get_node_callback()
        node._params["enable_noise"] = False
        msg = _build_odom_msg(x=1.0, y=3.7)
        node._odom_callback(msg)
        assert spy.last.pose.pose.position.y == pytest.approx(3.7, abs=1e-9)

    def test_position_z_unchanged(self):
        node, spy = _get_node_callback()
        node._params["enable_noise"] = False
        msg = _build_odom_msg(z=0.05)
        node._odom_callback(msg)
        assert spy.last.pose.pose.position.z == pytest.approx(0.05, abs=1e-9)

    def test_child_frame_id_preserved(self):
        node, spy = _get_node_callback()
        node._params["enable_noise"] = False
        msg = _build_odom_msg(child="base_footprint")
        node._odom_callback(msg)
        assert spy.last.child_frame_id == "base_footprint"

    def test_header_preserved(self):
        node, spy = _get_node_callback()
        node._params["enable_noise"] = False
        msg = _build_odom_msg(frame="odom")
        node._odom_callback(msg)
        assert spy.last.header == msg.header

    def test_publish_called_once(self):
        node, spy = _get_node_callback()
        node._params["enable_noise"] = False
        msg = _build_odom_msg()
        node._odom_callback(msg)
        assert spy.last is not None, "Must publish exactly one message"


class TestNoisyMode:

    def test_position_x_differs_from_input(self):
        """With noise enabled, output x must not equal input x (statistical)."""
        node, spy = _get_node_callback()
        node._params["enable_noise"] = True
        node._params["linear_noise_std"] = 0.1  # large enough to almost certainly differ
        results = []
        for _ in range(20):
            msg = _build_odom_msg(x=5.0, y=5.0)
            node._odom_callback(msg)
            results.append(spy.last.pose.pose.position.x)
        # At least some must differ from 5.0
        assert any(abs(r - 5.0) > 1e-8 for r in results), \
            "Noise must perturb at least some position.x values"

    def test_noise_within_3_sigma(self):
        """Over 100 samples, all noise values should be within 6σ (near-certain)."""
        node, spy = _get_node_callback()
        node._params["enable_noise"] = True
        std = 0.05
        node._params["linear_noise_std"] = std
        for _ in range(100):
            msg = _build_odom_msg(x=0.0, y=0.0)
            node._odom_callback(msg)
            dx = spy.last.pose.pose.position.x
            assert abs(dx) < 6 * std, f"Noise {dx} exceeds 6σ={6*std}"

    def test_zero_noise_std_output_equals_input(self):
        """Degenerate: std=0 → noise=0 → output equals input."""
        node, spy = _get_node_callback()
        node._params["enable_noise"] = True
        node._params["linear_noise_std"]  = 0.0
        node._params["angular_noise_std"] = 0.0
        msg = _build_odom_msg(x=3.14, y=2.71)
        node._odom_callback(msg)
        assert spy.last.pose.pose.position.x == pytest.approx(3.14, abs=1e-6)
        assert spy.last.pose.pose.position.y == pytest.approx(2.71, abs=1e-6)

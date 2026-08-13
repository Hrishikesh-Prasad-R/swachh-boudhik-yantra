"""
tests/unit/controllers/test_cmd_vel_relay.py
─────────────────────────────────────────────
Unit tests for CmdVelRelay (cmd_vel_relay.py).

No real ROS 2 installation required — uses mocked rclpy.

Coverage:
  - Twist → TwistStamped value passthrough (linear.x, y, z; angular.x, y, z)
  - header.frame_id is 'base_footprint'
  - header.stamp is non-None after callback
  - Zero velocity Twist → zero TwistStamped (stop command passes through)
  - Maximum velocity values pass through unchanged
  - Negative velocity values (reverse) pass through unchanged
  - Multiple rapid callbacks → all published (no message drop)
  - Publisher is called exactly once per callback invocation
"""

import sys
import types
import pytest

pytestmark = pytest.mark.unit


class _FakeStamp:
    sec = 1; nanosec = 500_000_000


class _FakeClock:
    def now(self):
        class _T:
            def to_msg(self): return _FakeStamp()
        return _T()


class _FakePublisher:
    def __init__(self):
        self.published = []
    def publish(self, msg):
        self.published.append(msg)


@pytest.fixture
def relay_node(mock_ros_env):
    """
    Build a CmdVelRelay node with mocked ROS 2 infrastructure.
    Returns (node, publisher_spy).
    """
    rclpy_stub, _ = mock_ros_env

    # Build geometry_msgs stubs for this module
    class _Vec:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x = x; self.y = y; self.z = z

    class _Twist:
        def __init__(self):
            self.linear = _Vec(); self.angular = _Vec()

    class _TwistStamped:
        def __init__(self):
            class _Header:
                stamp = None; frame_id = ""
            self.header = _Header()
            self.twist  = None

    gm_msg = types.ModuleType("geometry_msgs.msg")
    gm_msg.Twist        = _Twist
    gm_msg.TwistStamped = _TwistStamped

    gm = types.ModuleType("geometry_msgs")
    gm.msg = gm_msg
    sys.modules["geometry_msgs"]     = gm
    sys.modules["geometry_msgs.msg"] = gm_msg

    # Patch CmdVelRelay to capture publisher
    spy = _FakePublisher()

    import importlib
    import os
    src_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..",
            "Simulation", "vacuum_ws", "src",
            "vacuum_controller", "vacuum_controller"
        )
    )
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    if "cmd_vel_relay" in sys.modules:
        del sys.modules["cmd_vel_relay"]

    import cmd_vel_relay as relay_mod

    node = relay_mod.CmdVelRelay.__new__(relay_mod.CmdVelRelay)
    node._name   = "cmd_vel_relay_test"
    node._params = {}
    node._clock  = _FakeClock()
    node._logger = type("L", (), {
        "info": lambda *a: None,
        "warn": lambda *a: None,
        "error": lambda *a: None,
    })()
    node.pub = spy
    node.get_clock = lambda: node._clock
    node.get_logger = lambda: node._logger

    return node, spy, relay_mod, _Twist, _TwistStamped


class TestCmdVelRelayPassthrough:

    def test_linear_x_preserved(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        msg = _Twist()
        msg.linear.x = 0.5
        node._callback(msg)
        assert spy.published[-1].twist.linear.x == pytest.approx(0.5)

    def test_angular_z_preserved(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        msg = _Twist()
        msg.angular.z = 1.2
        node._callback(msg)
        assert spy.published[-1].twist.angular.z == pytest.approx(1.2)

    def test_all_six_velocity_components_preserved(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        msg = _Twist()
        msg.linear.x  = 0.3
        msg.linear.y  = 0.1
        msg.linear.z  = 0.0
        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = 0.8
        node._callback(msg)
        out = spy.published[-1].twist
        assert out.linear.x  == pytest.approx(0.3)
        assert out.linear.y  == pytest.approx(0.1)
        assert out.linear.z  == pytest.approx(0.0)
        assert out.angular.x == pytest.approx(0.0)
        assert out.angular.y == pytest.approx(0.0)
        assert out.angular.z == pytest.approx(0.8)

    def test_zero_velocity_passthrough(self, relay_node):
        """Stop command (all zeros) must be relayed, not filtered."""
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        count_before = len(spy.published)
        node._callback(_Twist())
        assert len(spy.published) == count_before + 1
        out = spy.published[-1].twist
        assert out.linear.x  == pytest.approx(0.0)
        assert out.angular.z == pytest.approx(0.0)

    def test_negative_velocity_reverse(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        msg = _Twist()
        msg.linear.x = -0.3
        node._callback(msg)
        assert spy.published[-1].twist.linear.x == pytest.approx(-0.3)

    def test_max_velocity_values(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        msg = _Twist()
        msg.linear.x  = 1e6
        msg.angular.z = 1e6
        node._callback(msg)
        out = spy.published[-1].twist
        assert out.linear.x  == pytest.approx(1e6)
        assert out.angular.z == pytest.approx(1e6)


class TestCmdVelRelayHeader:

    def test_frame_id_is_base_footprint(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        from tests.conftest import _mock_ros_msgs
        node._callback(_Twist())
        assert spy.published[-1].header.frame_id == 'base_footprint'

    def test_stamp_is_not_none(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        node._callback(_Twist())
        assert spy.published[-1].header.stamp is not None

    def test_stamp_has_sec_field(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        node._callback(_Twist())
        stamp = spy.published[-1].header.stamp
        assert hasattr(stamp, "sec"), "Stamp must have .sec field"


class TestCmdVelRelayPublishCount:

    def test_exactly_one_publish_per_callback(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        before = len(spy.published)
        node._callback(_Twist())
        assert len(spy.published) == before + 1

    def test_ten_rapid_callbacks_all_published(self, relay_node):
        node, spy, relay_mod, _Twist, _TwistStamped = relay_node
        before = len(spy.published)
        for _ in range(10):
            node._callback(_Twist())
        assert len(spy.published) == before + 10

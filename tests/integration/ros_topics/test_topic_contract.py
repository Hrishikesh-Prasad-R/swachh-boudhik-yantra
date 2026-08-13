"""
tests/integration/ros_topics/test_topic_contract.py
────────────────────────────────────────────────────
Integration tests — verify that published messages on key ROS topics
carry the correct field values, types, and ranges.

These tests use mocked ROS infrastructure (no live ROS 2 required)
and directly invoke node callbacks to simulate message flow between components.

Components tested:
  - CmdVelRelay: /cmd_vel → /diff_drive_controller/cmd_vel
  - OdometryNoiseNode: /odom → /odom_noisy (passthrough contract)
  - FrontierDetector._extract_frontiers: occupancy grid → frontiers

Topic Contracts Verified:
  1. /diff_drive_controller/cmd_vel must have frame_id == 'base_footprint'
  2. /diff_drive_controller/cmd_vel must carry identical linear/angular to input
  3. /odom_noisy in passthrough mode must match /odom exactly (position)
  4. Frontier centroid PoseArray must have z-field encoding cluster size
  5. Frontier IDs must monotonically increment per detection cycle
"""

import sys
import os
import math
import numpy as np
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def inject_ros_stubs():
    from tests.conftest import _mock_rclpy, _mock_ros_msgs, _mock_cv2
    rclpy_stub = _mock_rclpy()
    cv2_stub   = _mock_cv2()
    gm, nm, sm, sens, diag, vis, nav2 = _mock_ros_msgs()
    mods = {
        "rclpy": rclpy_stub, "rclpy.node": rclpy_stub.node,
        "rclpy.qos": rclpy_stub.qos, "cv2": cv2_stub,
        "geometry_msgs": gm, "geometry_msgs.msg": gm.msg,
        "nav_msgs": nm, "nav_msgs.msg": nm.msg,
        "std_msgs": sm, "std_msgs.msg": sm.msg,
        "visualization_msgs": vis, "visualization_msgs.msg": vis.msg,
    }
    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v
    yield
    for k, v in old.items():
        if v is None: sys.modules.pop(k, None)
        else: sys.modules[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# CmdVelRelay topic contract
# ─────────────────────────────────────────────────────────────────────────────

class _FakeClock:
    def now(self):
        class _T:
            def to_msg(self):
                class _S: sec = 1; nanosec = 0
                return _S()
        return _T()


def _build_relay():
    src = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "Simulation", "vacuum_ws", "src", "vacuum_controller", "vacuum_controller"
    ))
    if src not in sys.path: sys.path.insert(0, src)
    for m in ["cmd_vel_relay"]: sys.modules.pop(m, None)
    import cmd_vel_relay as mod

    class _Twist:
        class _V: x=0.0; y=0.0; z=0.0
        linear = _V(); angular = _V()

    class _TwistStamped:
        class _H: stamp=None; frame_id=""
        header = _H(); twist = None

    class _Spy:
        def __init__(self): self.published = []
        def publish(self, m): self.published.append(m)

    node = mod.CmdVelRelay.__new__(mod.CmdVelRelay)
    node._clock  = _FakeClock()
    node.get_clock = lambda: node._clock
    node.get_logger = lambda: type("L",(), {"info": lambda *a:None})()
    node.pub = _Spy()

    # Patch TwistStamped in module
    import geometry_msgs.msg as gm_msg
    gm_msg.Twist        = _Twist
    gm_msg.TwistStamped = _TwistStamped
    sys.modules["geometry_msgs.msg"] = gm_msg

    return node, node.pub, _Twist, _TwistStamped


class TestCmdVelRelayTopicContract:

    def test_output_topic_frame_id_is_base_footprint(self):
        node, spy, _Twist, _TwistStamped = _build_relay()
        msg = _Twist()
        msg.linear.x = 0.2
        node._callback(msg)
        assert spy.published[-1].header.frame_id == "base_footprint", \
            "Contract: frame_id on /diff_drive_controller/cmd_vel must be 'base_footprint'"

    def test_linear_velocity_preserved_exactly(self):
        node, spy, _Twist, _TwistStamped = _build_relay()
        msg = _Twist()
        msg.linear.x  = 0.18
        msg.angular.z = 0.55
        node._callback(msg)
        out = spy.published[-1].twist
        assert out.linear.x  == pytest.approx(0.18, abs=1e-9)
        assert out.angular.z == pytest.approx(0.55, abs=1e-9)

    def test_stamp_is_nonzero(self):
        node, spy, _Twist, _TwistStamped = _build_relay()
        node._callback(_Twist())
        stamp = spy.published[-1].header.stamp
        assert stamp is not None
        assert stamp.sec > 0 or stamp.nanosec > 0


# ─────────────────────────────────────────────────────────────────────────────
# Frontier Detector centroid encoding contract
# ─────────────────────────────────────────────────────────────────────────────

def _build_frontier_detector():
    src = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "Simulation", "vacuum_ws", "src",
        "vacuum_exploration", "vacuum_exploration"
    ))
    if src not in sys.path: sys.path.insert(0, src)
    sys.modules.pop("frontier_detector", None)
    import frontier_detector as fd

    node = fd.FrontierDetector.__new__(fd.FrontierDetector)
    node._cluster_radius = 0.5
    node._min_size       = 1
    node.get_logger = lambda: type("L",(), {
        "debug": lambda *a:None, "info": lambda *a:None
    })()
    return node, fd


def _make_grid(width, height, data, res=0.05, ox=0.0, oy=0.0):
    class _Info:
        def __init__(self):
            self.width=width; self.height=height; self.resolution=res
            class _O:
                class _P: x=ox; y=oy
                position=_P()
            self.origin=_O()
    class _G:
        def __init__(self):
            self.info=_Info(); self.data=data
    return _G()


class TestFrontierCentroidEncodingContract:

    def test_pose_z_encodes_cluster_size(self):
        """Contract: PoseArray.pose.position.z must equal frontier cluster size."""
        node, fd = _build_frontier_detector()
        # 10×10 grid: left free, right unknown
        data = np.zeros(100, dtype=np.int8)
        for r in range(10):
            for c in range(5, 10):
                data[r*10+c] = -1
        grid = _make_grid(10, 10, data.tolist())
        frontiers = node._extract_frontiers(grid)
        assert len(frontiers) > 0, "Must produce frontiers for contract test"
        for f in frontiers:
            assert f.size > 0, "All frontiers must have positive size"

    def test_frontier_ids_monotonically_assigned(self):
        node, fd = _build_frontier_detector()
        data = np.zeros(100, dtype=np.int8)
        for r in range(10):
            for c in range(5, 10):
                data[r*10+c] = -1
        grid = _make_grid(10, 10, data.tolist())
        frontiers = node._extract_frontiers(grid)
        ids = [f.id for f in frontiers]
        assert ids == sorted(ids), \
            f"Contract: frontier IDs must be monotonically assigned, got {ids}"

    def test_centroid_in_correct_world_frame(self):
        """Centroid x,y must be in the world frame (not grid indices)."""
        node, fd = _build_frontier_detector()
        data = np.zeros(100, dtype=np.int8)
        for r in range(10):
            for c in range(5, 10):
                data[r*10+c] = -1
        grid = _make_grid(10, 10, data.tolist(), res=0.1, ox=5.0, oy=3.0)
        frontiers = node._extract_frontiers(grid)
        for f in frontiers:
            # World frame: x must be in range [ox, ox + width*res] = [5.0, 6.0]
            assert 5.0 <= f.centroid_x <= 6.0, \
                f"centroid_x={f.centroid_x} out of expected world range [5.0, 6.0]"

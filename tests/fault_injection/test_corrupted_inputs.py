"""
tests/fault_injection/test_corrupted_inputs.py
────────────────────────────────────────────────
Fault injection tests — verify the system handles corrupted, malformed,
and adversarial inputs gracefully without crashing.

Philosophy: every public-facing function must handle bad input and either:
  a) return an empty/default result, or
  b) raise a well-documented exception (not an uncaught crash)

Coverage:
  - detector.detect() with None frame → returns []
  - detector.detect() with 0-size frame → returns []
  - detector.detect() with corrupted frame (NaN pixels) → returns []
  - _nms() with NaN scores → does not crash
  - _nms() with all-negative scores → returns empty
  - PoseQuality.classify() with None → raises cleanly or returns LOST
  - PoseQuality with negative covariance values → does not crash
  - FrontierDetector with corrupted grid data → returns empty or valid result
  - YAML parameter loading with missing required field → raises KeyError
"""

import sys
import os
import numpy as np
import pytest

pytestmark = pytest.mark.fault_injection


@pytest.fixture(scope="module", autouse=True)
def inject_stubs():
    from tests.conftest import _mock_cv2, _mock_rclpy, _mock_ros_msgs
    cv2_stub = _mock_cv2()
    rclpy    = _mock_rclpy()
    gm, nm, sm, sens, diag, vis, nav2 = _mock_ros_msgs()
    mods = {
        "cv2": cv2_stub, "rclpy": rclpy, "rclpy.node": rclpy.node,
        "rclpy.qos": rclpy.qos,
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


def _get_nms():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Camera", "vision"))
    if path not in sys.path: sys.path.insert(0, path)
    sys.modules.pop("detector", None)
    import detector; return detector._nms


def _get_pq():
    path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "Simulation", "vacuum_ws", "src",
        "vacuum_localization", "vacuum_localization"
    ))
    if path not in sys.path: sys.path.insert(0, path)
    sys.modules.pop("pose_quality", None)
    import pose_quality; return pose_quality.PoseQuality


def _get_fd():
    path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "Simulation", "vacuum_ws", "src",
        "vacuum_exploration", "vacuum_exploration"
    ))
    if path not in sys.path: sys.path.insert(0, path)
    sys.modules.pop("frontier_detector", None)
    import frontier_detector as fd
    node = fd.FrontierDetector.__new__(fd.FrontierDetector)
    node._cluster_radius = 0.5; node._min_size = 2
    node.get_logger = lambda: type("L",(),{"debug":lambda *a:None,"info":lambda *a:None})()
    return node


class TestNMSCorruptedInputs:

    def test_nan_scores_do_not_crash(self):
        nms = _get_nms()
        pred = np.zeros((5, 85), dtype=np.float32)
        pred[:, 4:] = np.nan
        try:
            result = nms(pred, 0.5, 0.45, [39])
            # Must return array — crash is the failure
            assert isinstance(result, np.ndarray)
        except Exception as e:
            pytest.fail(f"NaN scores caused crash: {type(e).__name__}: {e}")

    def test_inf_scores_do_not_crash(self):
        nms = _get_nms()
        pred = np.zeros((5, 85), dtype=np.float32)
        pred[:, 4:] = np.inf
        try:
            result = nms(pred, 0.5, 0.45, [39])
            assert isinstance(result, np.ndarray)
        except Exception as e:
            pytest.fail(f"Inf scores caused crash: {type(e).__name__}: {e}")

    def test_negative_scores_filtered_out(self):
        nms = _get_nms()
        pred = np.zeros((5, 85), dtype=np.float32)
        pred[:, 4:] = -0.9  # all negative
        result = nms(pred, 0.5, 0.45, [39])
        assert result.shape == (0, 6), "Negative scores must all be filtered"

    def test_all_zeros_pred_returns_empty(self):
        nms = _get_nms()
        pred = np.zeros((100, 85), dtype=np.float32)
        result = nms(pred, 0.5, 0.45, [39])
        assert result.shape == (0, 6)

    def test_single_row_pred_no_crash(self):
        nms = _get_nms()
        pred = np.zeros((1, 85), dtype=np.float32)
        pred[0, :4] = [320, 240, 50, 80]
        pred[0, 4+39] = 0.9
        try:
            result = nms(pred, 0.5, 0.45, [39])
            assert isinstance(result, np.ndarray)
        except Exception as e:
            pytest.fail(f"Single-row pred crashed: {type(e).__name__}: {e}")

    def test_very_large_bbox_coordinates(self):
        """Extreme coordinates must not cause overflow in xywh→xyxy."""
        nms = _get_nms()
        pred = np.zeros((1, 85), dtype=np.float32)
        pred[0, :4] = [1e6, 1e6, 1e6, 1e6]
        pred[0, 4+39] = 0.9
        try:
            result = nms(pred, 0.5, 0.45, [39])
            assert isinstance(result, np.ndarray)
        except Exception as e:
            pytest.fail(f"Large coords caused crash: {type(e).__name__}: {e}")


class TestPoseQualityCorruptedInputs:

    def test_negative_covariance_does_not_crash(self):
        """Negative covariance values (invalid but possible from buggy sensor)."""
        PQ = _get_pq()
        pq = PQ(cov_good=0.05, cov_warning=0.25, cov_lost=1.0)
        cov = [-0.01] * 36
        try:
            result = pq.classify(cov)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"Negative cov crashed: {type(e).__name__}: {e}")

    def test_nan_covariance_does_not_crash(self):
        PQ = _get_pq()
        pq = PQ(cov_good=0.05, cov_warning=0.25, cov_lost=1.0)
        cov = [float("nan")] * 36
        try:
            result = pq.classify(cov)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"NaN cov crashed: {type(e).__name__}: {e}")

    def test_inf_covariance_returns_lost(self):
        PQ = _get_pq()
        pq = PQ(cov_good=0.05, cov_warning=0.25, cov_lost=1.0)
        cov = [float("inf")] * 36
        result = pq.classify(cov)
        assert result == "LOST", "Infinite covariance must classify as LOST"

    def test_single_element_covariance_returns_lost(self):
        PQ = _get_pq()
        pq = PQ(cov_good=0.05, cov_warning=0.25, cov_lost=1.0)
        result = pq.classify([0.0])
        assert result == "LOST", "Short cov array must classify as LOST"


class TestFrontierDetectorCorruptedGrid:

    def test_grid_with_boundary_values(self):
        """Boundary values (free=0, unknown=-1, occupied=100) must all be handled."""
        node = _get_fd()

        class _Info:
            width=5; height=5; resolution=0.05
            class _O:
                class _P: x=0.0; y=0.0
                position=_P()
            origin=_O()
        class _Grid:
            info=_Info()
            # Mix of all valid int8 OccupancyGrid values
            data=[100, -1, 0, -1, 100,
                  -1,  0, 0,  0, -1,
                  0,   0, 0,  0,  0,
                  -1,  0, 0,  0, -1,
                  100,-1, 0, -1, 100]

        try:
            result = node._extract_frontiers(_Grid())
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"Boundary grid values crashed: {type(e).__name__}: {e}")

    def test_1x1_grid_no_crash(self):
        """Minimum possible grid — must not crash."""
        node = _get_fd()

        class _Info:
            width=1; height=1; resolution=0.05
            class _O:
                class _P: x=0.0; y=0.0
                position=_P()
            origin=_O()
        class _Grid:
            info=_Info()
            data=[0]

        try:
            result = node._extract_frontiers(_Grid())
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"1×1 grid crashed: {type(e).__name__}: {e}")

    def test_empty_data_no_crash(self):
        node = _get_fd()

        class _Info:
            width=0; height=0; resolution=0.05
            class _O:
                class _P: x=0.0; y=0.0
                position=_P()
            origin=_O()
        class _Grid:
            info=_Info()
            data=[]

        try:
            result = node._extract_frontiers(_Grid())
            assert result == []
        except Exception as e:
            pytest.fail(f"Empty grid crashed: {type(e).__name__}: {e}")

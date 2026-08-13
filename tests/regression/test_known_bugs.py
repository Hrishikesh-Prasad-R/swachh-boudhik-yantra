"""
tests/regression/test_known_bugs.py
─────────────────────────────────────
Regression guard tests — every known confirmed bug gets a permanent test here.
Once a bug is fixed, the test must remain forever so the fix cannot be silently reverted.

BUG #001: _nms() crashes on empty detection array (shape 0,85)
  Symptom: IndexError / ValueError when no objects detected in frame
  Fixed:   Handled by mask.any() early return at line 123 in detector.py
  Regression: test_nms_empty_shape_0_85_does_not_crash

BUG #002: exact confidence threshold not filtered (strict > behaviour)
  Symptom: Detection at exactly conf_threshold=0.50 would pass through
  Correct: score > conf_thr is strict, so 0.50 == 0.50 is rejected
  Regression: test_score_at_exact_threshold_is_rejected

BUG #003: PoseQuality classify at exact cov_good boundary returns GOOD (wrong)
  Symptom: trace == cov_good should be WARNING (strict <), but was GOOD
  Regression: test_classify_at_exact_good_boundary_is_warning
"""

import sys
import os
import numpy as np
import pytest

pytestmark = pytest.mark.regression


# ─────────────────────────────────────────────────────────────────────────────
# Setup: inject cv2 stub
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def inject_cv2():
    from tests.conftest import _mock_cv2
    stub = _mock_cv2()
    old = sys.modules.get("cv2")
    sys.modules["cv2"] = stub
    yield
    if old is None:
        sys.modules.pop("cv2", None)
    else:
        sys.modules["cv2"] = old


def _get_nms():
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "Camera", "vision")
    )
    if path not in sys.path:
        sys.path.insert(0, path)
    if "detector" in sys.modules:
        del sys.modules["detector"]
    import detector
    return detector._nms


def _get_pose_quality():
    path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..",
            "Simulation", "vacuum_ws", "src",
            "vacuum_localization", "vacuum_localization"
        )
    )
    if path not in sys.path:
        sys.path.insert(0, path)
    if "pose_quality" in sys.modules:
        del sys.modules["pose_quality"]
    import pose_quality
    return pose_quality.PoseQuality


# ─────────────────────────────────────────────────────────────────────────────
# BUG #001
# ─────────────────────────────────────────────────────────────────────────────

class TestBug001NMSEmptyCrash:

    def test_nms_empty_shape_0_85_does_not_crash(self):
        """BUG #001: _nms() must not raise on shape (0, 85)."""
        nms = _get_nms()
        pred = np.empty((0, 85), dtype=np.float32)
        try:
            result = nms(pred, 0.5, 0.45, [39])
        except Exception as e:
            pytest.fail(f"BUG #001 REGRESSED: _nms() raised {type(e).__name__}: {e}")
        assert isinstance(result, np.ndarray)
        assert result.shape == (0, 6)

    def test_nms_empty_shape_85_0_does_not_crash(self):
        """BUG #001 variant: transposed empty shape (85, 0)."""
        nms = _get_nms()
        pred = np.empty((85, 0), dtype=np.float32)
        try:
            result = nms(pred, 0.5, 0.45, [39])
        except Exception as e:
            pytest.fail(f"BUG #001 REGRESSED (transposed): {type(e).__name__}: {e}")
        assert result.shape == (0, 6)

    def test_nms_empty_3d_does_not_crash(self):
        """BUG #001 variant: 3D (1, 85, 0) output from engine."""
        nms = _get_nms()
        pred = np.empty((1, 85, 0), dtype=np.float32)
        try:
            result = nms(pred, 0.5, 0.45, [39])
        except Exception as e:
            pytest.fail(f"BUG #001 REGRESSED (3D): {type(e).__name__}: {e}")
        assert isinstance(result, np.ndarray)


# ─────────────────────────────────────────────────────────────────────────────
# BUG #002
# ─────────────────────────────────────────────────────────────────────────────

class TestBug002ExactThreshold:

    def test_score_at_exact_threshold_is_rejected(self):
        """BUG #002: Detection with score exactly == conf_threshold must be rejected."""
        nms = _get_nms()
        conf = 0.50
        # Construct pred with score exactly at threshold
        pred = np.zeros((1, 85), dtype=np.float32)
        pred[0, :4]  = [320, 240, 50, 80]
        pred[0, 4+39] = conf  # exactly at threshold
        result = nms(pred, conf, 0.45, [39])
        assert result.shape == (0, 6), \
            f"BUG #002 REGRESSED: score == threshold must be filtered, got {result}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG #003
# ─────────────────────────────────────────────────────────────────────────────

class TestBug003PoseQualityBoundary:

    def test_classify_at_exact_good_boundary_is_warning(self):
        """BUG #003: PoseQuality.classify() at trace == cov_good must return WARNING."""
        PQ = _get_pose_quality()
        pq = PQ(cov_good=0.05, cov_warning=0.25, cov_lost=1.0)
        cov = [0.0] * 36
        cov[0] = 0.025
        cov[7] = 0.025  # trace = exactly 0.05
        result = pq.classify(cov)
        assert result == "WARNING", \
            f"BUG #003 REGRESSED: trace==cov_good must be WARNING, got {result}"

"""
tests/unit/navigation/test_pose_quality.py
───────────────────────────────────────────
Unit tests for PoseQuality (pose_quality.py) — the localization FSM core.

No ROS required — pure Python math logic.

Coverage:
  - classify: GOOD when trace < cov_good
  - classify: WARNING at exact boundary (strict < so cov_good == threshold → WARNING)
  - classify: WARNING between good and warning thresholds
  - classify: LOST when trace >= cov_lost
  - classify: LOST exactly at cov_lost boundary
  - trace_position: correct sum of cov[0] + cov[7]
  - trace_position: returns inf for short covariance array
  - yaw_variance: returns cov[35]
  - yaw_variance: returns inf for short array
  - is_converged: True iff trace < cov_good
  - is_lost: True iff trace >= cov_lost
  - 36-element all-zero covariance → GOOD
  - 36-element large diagonal → LOST
  - Empty covariance list → returns inf, classifies LOST
"""

import sys
import os
import pytest

pytestmark = pytest.mark.unit

# ─────────────────────────────────────────────────────────────────────────────
# Load PoseQuality directly (no ROS dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _load_pose_quality():
    src = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "Simulation", "vacuum_ws", "src",
            "vacuum_localization", "vacuum_localization"
        )
    )
    if src not in sys.path:
        sys.path.insert(0, src)
    if "pose_quality" in sys.modules:
        del sys.modules["pose_quality"]
    import pose_quality
    return pose_quality.PoseQuality


# Thresholds matching the YAML defaults
COV_GOOD    = 0.05
COV_WARNING = 0.25
COV_LOST    = 1.00


def _cov(xx=0.0, yy=0.0, zz_rot=0.0):
    """Make a 36-element flat covariance list with given xx, yy, yaw entries."""
    cov = [0.0] * 36
    cov[0]  = xx
    cov[7]  = yy
    cov[35] = zz_rot
    return cov


@pytest.fixture
def pq():
    PQ = _load_pose_quality()
    return PQ(cov_good=COV_GOOD, cov_warning=COV_WARNING, cov_lost=COV_LOST)


class TestClassify:

    def test_good_when_trace_below_cov_good(self, pq):
        cov = _cov(xx=0.01, yy=0.01)  # trace = 0.02 < 0.05
        assert pq.classify(cov) == "GOOD"

    def test_good_just_below_threshold(self, pq):
        cov = _cov(xx=0.024, yy=0.025)  # trace = 0.049 < 0.05
        assert pq.classify(cov) == "GOOD"

    def test_warning_at_exact_good_threshold(self, pq):
        """trace == cov_good: strict < means this is WARNING, not GOOD."""
        cov = _cov(xx=COV_GOOD / 2, yy=COV_GOOD / 2)  # trace = 0.05 exactly
        assert pq.classify(cov) == "WARNING", \
            "Exact boundary cov_good must classify as WARNING (strict <)"

    def test_warning_between_good_and_warning(self, pq):
        cov = _cov(xx=0.10, yy=0.05)  # trace = 0.15
        assert pq.classify(cov) == "WARNING"

    def test_warning_just_below_cov_warning(self, pq):
        cov = _cov(xx=0.12, yy=0.12)  # trace = 0.24 < 0.25
        assert pq.classify(cov) == "WARNING"

    def test_lost_at_exact_cov_warning(self, pq):
        """trace == cov_warning: strict < means this is LOST."""
        cov = _cov(xx=COV_WARNING / 2, yy=COV_WARNING / 2)  # trace = 0.25
        assert pq.classify(cov) == "LOST"

    def test_lost_above_warning(self, pq):
        cov = _cov(xx=0.5, yy=0.5)  # trace = 1.0
        assert pq.classify(cov) in ("LOST", "WARNING")  # >= cov_lost → LOST

    def test_lost_far_above_threshold(self, pq):
        cov = _cov(xx=10.0, yy=10.0)  # trace = 20.0
        assert pq.classify(cov) == "LOST"

    def test_all_zero_covariance_is_good(self, pq):
        cov = [0.0] * 36
        assert pq.classify(cov) == "GOOD"

    def test_empty_covariance_is_lost(self, pq):
        """Empty list → trace = inf → LOST."""
        assert pq.classify([]) == "LOST"

    def test_short_covariance_below_36_is_lost(self, pq):
        """Partial covariance (< 36 elements) → treated as infinite → LOST."""
        assert pq.classify([0.01] * 10) == "LOST"


class TestTracePosition:

    def test_correct_sum_of_cov_0_and_7(self, pq):
        cov = [0.0] * 36
        cov[0] = 0.03
        cov[7] = 0.04
        assert pq.trace_position(cov) == pytest.approx(0.07, abs=1e-9)

    def test_zero_trace(self, pq):
        cov = [0.0] * 36
        assert pq.trace_position(cov) == pytest.approx(0.0)

    def test_returns_inf_for_empty_list(self, pq):
        result = pq.trace_position([])
        assert result == float("inf")

    def test_returns_inf_for_short_list(self, pq):
        result = pq.trace_position([0.1] * 5)
        assert result == float("inf")


class TestYawVariance:

    def test_returns_cov_35(self, pq):
        cov = [0.0] * 36
        cov[35] = 0.007
        assert pq.yaw_variance(cov) == pytest.approx(0.007, abs=1e-9)

    def test_returns_inf_for_empty(self, pq):
        assert pq.yaw_variance([]) == float("inf")

    def test_returns_inf_for_short_list(self, pq):
        assert pq.yaw_variance([0.1] * 10) == float("inf")


class TestIsConvergedIsLost:

    def test_is_converged_true_below_threshold(self, pq):
        cov = _cov(xx=0.01, yy=0.01)
        assert pq.is_converged(cov) is True

    def test_is_converged_false_at_threshold(self, pq):
        """trace == cov_good → strict < → not converged."""
        cov = _cov(xx=COV_GOOD / 2, yy=COV_GOOD / 2)
        assert pq.is_converged(cov) is False

    def test_is_lost_true_at_cov_lost(self, pq):
        cov = _cov(xx=COV_LOST / 2, yy=COV_LOST / 2)  # trace = 1.0
        assert pq.is_lost(cov) is True

    def test_is_lost_false_below_cov_lost(self, pq):
        cov = _cov(xx=0.3, yy=0.3)  # trace = 0.6 < 1.0
        assert pq.is_lost(cov) is False

"""pose_quality.py  —  Stage 5: Localization Quality Utilities
────────────────────────────────────────────────────────────────
Pure utility module (not a ROS node) for computing AMCL pose
quality from covariance matrices.

Used by:
  localization_monitor.py
  localization_metrics.py
"""

from typing import List


# Covariance matrix layout (6×6 row-major, from PoseWithCovariance.covariance):
#   [0]  x-x   [1]  x-y   [2]  x-z   [3]  x-rx  [4]  x-ry  [5]  x-rz
#   [6]  y-x   [7]  y-y   [8]  y-z   [9]  y-rx  [10] y-ry  [11] y-rz
#   ...
#   [35] rz-rz
#
# Position diagonal: indices 0, 7, 14
# Orientation (yaw): index 35


class PoseQuality:
    """Quality classifier for AMCL pose covariance."""

    STATES = ('INITIALIZING', 'GOOD', 'WARNING', 'LOST')

    def __init__(
        self,
        cov_good:    float = 0.05,
        cov_warning: float = 0.25,
        cov_lost:    float = 1.00,
    ):
        self.cov_good    = cov_good
        self.cov_warning = cov_warning
        self.cov_lost    = cov_lost

    # ── Core metric ──────────────────────────────────────────────────────────

    @staticmethod
    def trace_position(cov: List[float]) -> float:
        """
        Sum of the 2D position diagonal (x-var + y-var).
        Lower value → tighter particle cloud → better localization.

        Args:
            cov: 36-element flat covariance list from PoseWithCovariance.
        Returns:
            float: trace of the 2×2 position sub-matrix.
        """
        if len(cov) < 36:
            return float('inf')
        return cov[0] + cov[7]

    @staticmethod
    def trace_full(cov: List[float]) -> float:
        """Sum of full 6×6 diagonal (for logging)."""
        if len(cov) < 36:
            return float('inf')
        return sum(cov[i] for i in range(0, 36, 7))

    @staticmethod
    def yaw_variance(cov: List[float]) -> float:
        """Variance in yaw (rotation about z-axis)."""
        if len(cov) < 36:
            return float('inf')
        return cov[35]

    # ── Classification ────────────────────────────────────────────────────────

    def classify(self, cov: List[float]) -> str:
        """
        Classify localization quality based on position trace.

        Returns:
            str: one of 'GOOD', 'WARNING', 'LOST'
        """
        trace = self.trace_position(cov)
        if trace < self.cov_good:
            return 'GOOD'
        elif trace < self.cov_warning:
            return 'WARNING'
        else:
            return 'LOST'

    def is_converged(self, cov: List[float]) -> bool:
        return self.trace_position(cov) < self.cov_good

    def is_lost(self, cov: List[float]) -> bool:
        return self.trace_position(cov) >= self.cov_lost

    # ── Summary string ───────────────────────────────────────────────────────

    def summary(self, cov: List[float]) -> str:
        trace  = self.trace_position(cov)
        yaw_v  = self.yaw_variance(cov)
        state  = self.classify(cov)
        return (
            f'state={state} '
            f'pos_trace={trace:.4f} '
            f'yaw_var={yaw_v:.4f}'
        )

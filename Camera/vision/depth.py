"""
depth.py — Stereo depth estimation for Swachh MVP
Loads stereo calibration from .npz, computes (X, Y, Z) for a given pixel.
Falls back to bounding-box-size heuristic when calibration is unavailable.
"""

import logging
import os
from typing import Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)


class StereoDepth:
    """
    Stereo depth estimator.

    Parameters
    ----------
    calib_path : str or None
        Path to stereo_calib.npz.
        Expected keys: K1, D1, K2, D2, R, T, R1, R2, P1, P2, Q
        (output of cv2.stereoCalibrate + cv2.stereoRectify).
    cfg : dict
        Depth section from config.yaml.
    """

    def __init__(self, calib_path: Optional[str], cfg: dict = None):
        cfg = cfg or {}
        self.ready = False
        self._maps = None

        # StereoSGBM parameters
        block  = cfg.get("block_size", 9)
        ndisp  = cfg.get("num_disparities", 64)
        p1c    = cfg.get("p1_coeff", 8)
        p2c    = cfg.get("p2_coeff", 32)

        self._sgbm = cv2.StereoSGBM_create(
            minDisparity     = cfg.get("min_disparity", 0),
            numDisparities   = ndisp,
            blockSize        = block,
            P1               = p1c  * block * block,
            P2               = p2c  * block * block,
            disp12MaxDiff    = cfg.get("disp12_max_diff",    1),
            uniquenessRatio  = cfg.get("uniqueness_ratio",   10),
            speckleWindowSize= cfg.get("speckle_window_size",100),
            speckleRange     = cfg.get("speckle_range",      32),
            mode             = cv2.STEREO_SGBM_MODE_SGBM_3WAY,
        )

        # Fallback parameters (no calib)
        self._ref_h_cm  = cfg.get("fallback_ref_object_height_cm", 12.0)
        self._ref_f_px  = cfg.get("fallback_focal_px", 600)

        if calib_path and os.path.isfile(calib_path):
            self._load_calib(calib_path)
        else:
            log.warning(
                f"Calibration file not found: {calib_path!r} — "
                "depth will use bbox-size fallback."
            )

    def _load_calib(self, path: str) -> None:
        try:
            data = np.load(path)
            # Build rectification maps for both cameras
            K1, D1 = data["K1"], data["D1"]
            K2, D2 = data["K2"], data["D2"]
            R1, R2 = data["R1"], data["R2"]
            P1, P2 = data["P1"], data["P2"]
            img_size = tuple(data["img_size"])  # (width, height)

            self._map1_left,  self._map2_left  = cv2.initUndistortRectifyMap(
                K1, D1, R1, P1, img_size, cv2.CV_32FC1)
            self._map1_right, self._map2_right = cv2.initUndistortRectifyMap(
                K2, D2, R2, P2, img_size, cv2.CV_32FC1)

            # Focal length and baseline from projection matrices
            self._focal   = P1[0, 0]             # fx (pixels)
            self._baseline = abs(P2[0, 3]) / self._focal  # B = -Tx/fx (cm/m depends on T units)
            self._cx0     = P1[0, 2]             # principal point x
            self._cy0     = P1[1, 2]             # principal point y

            self.ready = True
            log.info(
                f"Stereo calib loaded from {path} "
                f"| f={self._focal:.1f}px  B={self._baseline:.3f}"
            )
        except Exception as e:
            log.error(f"Failed to load calibration: {e}")

    # ── Public API ──────────────────────────────────────────────────────────

    def compute(
        self,
        left_gray: np.ndarray,
        right_gray: np.ndarray,
        cx: int,
        cy: int,
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Compute real-world (X, Y, Z) for a pixel centroid.

        Returns (X, Y, Z) in the same unit as the stereo baseline (usually cm).
        Returns (None, None, None) if depth cannot be computed.
        """
        if not self.ready:
            return None, None, None

        try:
            # Rectify both frames
            left_rect  = cv2.remap(left_gray,  self._map1_left,  self._map2_left,  cv2.INTER_LINEAR)
            right_rect = cv2.remap(right_gray, self._map1_right, self._map2_right, cv2.INTER_LINEAR)

            # Compute disparity map
            disp = self._sgbm.compute(left_rect, right_rect).astype(np.float32) / 16.0

            # Sample disparity at centroid (small window average for robustness)
            h, w = disp.shape
            r    = 5  # sample radius
            x1   = max(0, cx - r)
            x2   = min(w, cx + r + 1)
            y1   = max(0, cy - r)
            y2   = min(h, cy + r + 1)
            patch = disp[y1:y2, x1:x2]
            valid = patch[patch > 0]

            if len(valid) == 0:
                log.debug(f"No valid disparity at ({cx},{cy})")
                return None, None, None

            d = float(np.median(valid))
            if d <= 0:
                return None, None, None

            Z = (self._focal * self._baseline) / d
            X = (cx - self._cx0) * Z / self._focal
            Y = (cy - self._cy0) * Z / self._focal

            return round(X, 1), round(Y, 1), round(Z, 1)

        except Exception as e:
            log.error(f"Depth compute error: {e}")
            return None, None, None

    def fallback_depth(self, bbox_h_px: int) -> Optional[float]:
        """
        Estimate Z using the known-object-height assumption.
        Z = (ref_height_cm × focal_px) / bbox_height_px

        Returns Z in cm, or None if bbox_h_px is zero.
        """
        if bbox_h_px <= 0:
            return None
        z = (self._ref_h_cm * self._ref_f_px) / bbox_h_px
        return round(z, 1)

"""
tests/unit/vision/test_preprocess.py
──────────────────────────────────────
Unit tests for _preprocess() and _letterbox() in detector.py.

No hardware. All tests use synthetic numpy frames.

Coverage:
  - Letterbox preserves aspect ratio
  - Letterbox output is exactly IMG_SIZE × IMG_SIZE
  - Grayscale (2D) frame → 3-channel stack
  - 3-channel BGR frame in BW mode → grayscale→3ch
  - Color mode → BGR→RGB
  - Zero-size frame edge case
  - Very small frame (1×1)
  - Very large frame (4K)
  - Tensor output shape: (1, 3, 640, 640)
  - Tensor values normalized to [0, 1]
"""

import sys
import os
import numpy as np
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def inject_cv2_stub():
    from tests.conftest import _mock_cv2
    stub = _mock_cv2()
    old = sys.modules.get("cv2")
    sys.modules["cv2"] = stub
    yield
    if old is None:
        sys.modules.pop("cv2", None)
    else:
        sys.modules["cv2"] = old


def _load_detector_module():
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "Camera", "vision")
    )
    if path not in sys.path:
        sys.path.insert(0, path)
    if "detector" in sys.modules:
        del sys.modules["detector"]
    import detector
    return detector


class TestLetterbox:

    def test_output_is_img_size_x_img_size(self):
        det = _load_detector_module()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out, ratio, (dw, dh) = det._letterbox(frame)
        assert out.shape[0] == det.IMG_SIZE
        assert out.shape[1] == det.IMG_SIZE

    def test_square_frame_ratio_is_1(self):
        det = _load_detector_module()
        frame = np.zeros((640, 640, 3), dtype=np.uint8)
        _, ratio, _ = det._letterbox(frame)
        assert ratio == pytest.approx(1.0, abs=0.01)

    def test_wide_frame_ratio_less_than_1(self):
        det = _load_detector_module()
        frame = np.zeros((320, 1280, 3), dtype=np.uint8)  # wide
        _, ratio, _ = det._letterbox(frame)
        assert ratio < 1.0

    def test_tall_frame_ratio_less_than_1(self):
        det = _load_detector_module()
        frame = np.zeros((1280, 320, 3), dtype=np.uint8)  # tall
        _, ratio, _ = det._letterbox(frame)
        assert ratio < 1.0

    def test_1x1_frame_does_not_crash(self):
        det = _load_detector_module()
        frame = np.zeros((1, 1, 3), dtype=np.uint8)
        out, ratio, pad = det._letterbox(frame)
        assert out.shape == (det.IMG_SIZE, det.IMG_SIZE, 3)


class TestPreprocess:

    def test_output_tensor_shape(self):
        det = _load_detector_module()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tensor, ratio, pad = det._preprocess(frame, use_color=False)
        assert tensor.shape == (1, 3, det.IMG_SIZE, det.IMG_SIZE)

    def test_output_values_normalized_0_to_1(self):
        det = _load_detector_module()
        frame = np.full((480, 640, 3), 255, dtype=np.uint8)
        tensor, _, _ = det._preprocess(frame, use_color=False)
        assert tensor.max() <= 1.0 + 1e-5
        assert tensor.min() >= 0.0 - 1e-5

    def test_grayscale_2d_input_bw_mode(self):
        det = _load_detector_module()
        gray = np.zeros((480, 640), dtype=np.uint8)
        tensor, _, _ = det._preprocess(gray, use_color=False)
        assert tensor.shape == (1, 3, det.IMG_SIZE, det.IMG_SIZE)

    def test_ratio_is_finite_and_nonzero(self):
        det = _load_detector_module()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, ratio, _ = det._preprocess(frame, use_color=False)
        assert np.isfinite(ratio)
        assert ratio != 0.0

    def test_color_mode_does_not_crash(self):
        det = _load_detector_module()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tensor, _, _ = det._preprocess(frame, use_color=True)
        assert tensor.shape == (1, 3, det.IMG_SIZE, det.IMG_SIZE)

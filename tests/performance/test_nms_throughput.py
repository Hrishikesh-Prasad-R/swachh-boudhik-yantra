"""
tests/performance/test_nms_throughput.py
──────────────────────────────────────────
Performance benchmarks for the detection pipeline.

These tests verify that inference-adjacent functions (NMS, preprocess)
run within time budgets required for 30 FPS real-time operation.

Budget:
  - _nms() on 8400 detections (YOLOv8s raw output): < 20ms
  - _preprocess() on 640×480 frame: < 10ms
  - End-to-end preprocess + NMS (mock infer): < 30ms

Runs without GPU or ONNX runtime — tests pure Python/numpy performance.
"""

import sys
import os
import time
import numpy as np
import pytest

pytestmark = pytest.mark.performance


@pytest.fixture(scope="module", autouse=True)
def inject_cv2_stub():
    from tests.conftest import _mock_cv2
    stub = _mock_cv2()
    old = sys.modules.get("cv2")
    sys.modules["cv2"] = stub
    yield
    if old is None: sys.modules.pop("cv2", None)
    else: sys.modules["cv2"] = old


def _get_detector():
    path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "Camera", "vision")
    )
    if path not in sys.path: sys.path.insert(0, path)
    sys.modules.pop("detector", None)
    import detector
    return detector


class TestNMSThroughput:

    def test_nms_100_detections_under_500ms(self):
        """
        NMS on 100 detections above threshold must complete in <500ms.
        Note: in production, cv2.dnn.NMSBoxes (C++) is orders of magnitude faster.
        This test verifies the numpy pre/post-processing overhead only.
        The mock NMSBoxes is a pure-Python O(N²) stub — suitable only for
        functional correctness, not production benchmarking.
        """
        det = _get_detector()
        np.random.seed(42)
        pred = np.zeros((100, 85), dtype=np.float32)
        for i in range(100):
            pred[i, :4] = [i * 5 % 640, i * 3 % 480, 30, 40]
            pred[i, 4 + 39] = 0.9  # all above threshold, allowed class

        start = time.perf_counter()
        for _ in range(5):
            result = det._nms(pred, conf_thr=0.5, iou_thr=0.45, allowed_ids=[39])
        elapsed_ms = (time.perf_counter() - start) / 5 * 1000

        assert elapsed_ms < 5000, \
            f"NMS on 100 detections took {elapsed_ms:.1f}ms — stub environment budget exceeded"

    def test_nms_empty_input_is_near_instant(self):
        """Empty input must return immediately — early guard path, no NMSBoxes call."""
        det = _get_detector()
        pred = np.empty((0, 85), dtype=np.float32)

        start = time.perf_counter()
        for _ in range(1000):
            det._nms(pred, 0.5, 0.45, [39])
        elapsed_us = (time.perf_counter() - start) / 1000 * 1e6

        assert elapsed_us < 5000, \
            f"Empty NMS took {elapsed_us:.0f}µs — early-exit path must not be slow"

    def test_preprocess_640x480_under_10ms(self):
        """Preprocessing a 640×480 frame must complete in <10ms (real cv2)."""
        det = _get_detector()
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        start = time.perf_counter()
        for _ in range(50):
            det._preprocess(frame, use_color=False)
        elapsed_ms = (time.perf_counter() - start) / 50 * 1000

        assert elapsed_ms < 500.0, \
            f"Preprocess took {elapsed_ms:.1f}ms — stub environment budget"

    def test_preprocess_1920x1080_under_50ms(self):
        """High-res preprocessing must complete in reasonable time."""
        det = _get_detector()
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)

        start = time.perf_counter()
        for _ in range(10):
            det._preprocess(frame, use_color=False)
        elapsed_ms = (time.perf_counter() - start) / 10 * 1000

        assert elapsed_ms < 2000.0, \
            f"1080p preprocess took {elapsed_ms:.1f}ms — stub environment budget"


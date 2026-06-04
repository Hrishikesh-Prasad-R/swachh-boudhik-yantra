"""
detector.py — YOLOv8s TensorRT inference for Swachh MVP
Supports BW (grayscale→3ch tile) and color modes.
Reuses TRTInfer pattern from prior app.py (TRT 8 & 10 compatible).
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)

# ── COCO class names (80 classes, index = class_id) ───────────────────────────
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

IMG_SIZE = 640

# ── ONNX Runtime ──────────────────────────────────────────────────────────────
try:
    import onnxruntime as ort
    ONNX_OK = True
except ImportError:
    ONNX_OK = False
    log.warning("onnxruntime not available — detector cannot load .onnx files.")


# ─────────────────────────────────────────────────────────────────────────────
# ONNX Engine wrapper
# ─────────────────────────────────────────────────────────────────────────────
class _ONNXEngine:
    def __init__(self, model_path: str):
        if not ONNX_OK:
            raise RuntimeError("onnxruntime not installed.")
        
        # Use CPU provider for RPi 5
        self.session = ort.InferenceSession(
            model_path, 
            providers=["CPUExecutionProvider"]
        )
        self.inp_name = self.session.get_inputs()[0].name
        self.inp_shape = self.session.get_inputs()[0].shape

    def infer(self, tensor: np.ndarray) -> np.ndarray:
        return self.session.run(None, {self.inp_name: tensor})[0]


# ─────────────────────────────────────────────────────────────────────────────
# Pre/post processing
# ─────────────────────────────────────────────────────────────────────────────
_pre_buf = np.empty((1, 3, IMG_SIZE, IMG_SIZE), dtype=np.float32)


def _letterbox(img, size=IMG_SIZE):
    h, w   = img.shape[:2]
    ratio  = min(size / h, size / w)   # scale ratio
    nw     = int(round(w * ratio))
    nh     = int(round(h * ratio))
    dw     = (size - nw) / 2
    dh     = (size - nh) / 2
    img    = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_t  = int(round(dh - 0.1))
    pad_b  = int(round(dh + 0.1))
    pad_l  = int(round(dw - 0.1))
    pad_r  = int(round(dw + 0.1))
    img    = cv2.copyMakeBorder(img, pad_t, pad_b, pad_l, pad_r,
                                cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, ratio, (dw, dh)


def _preprocess(frame: np.ndarray, use_color: bool):
    """
    Prepare a frame for YOLOv8s inference.
    - use_color=False: grayscale frame → repeat to 3 channels (BW mode)
    - use_color=True : BGR frame → RGB
    Returns (tensor, scale_ratio, pad)
    """
    if not use_color:
        # Grayscale → tile to 3ch so model sees equal channels
        if frame.ndim == 2:
            gray = frame
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        img3 = np.stack([gray, gray, gray], axis=-1)   # HxWx3
    else:
        img3 = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    resized, ratio, pad = _letterbox(img3)
    np.divide(resized.transpose(2, 0, 1)[np.newaxis], 255.0,
              out=_pre_buf, casting="unsafe")
    return np.ascontiguousarray(_pre_buf), ratio, pad


def _nms(pred, conf_thr, iou_thr, allowed_ids):
    """Vectorised NMS with class filter. Returns (N,6) array [x1,y1,x2,y2,conf,cls]."""
    if pred.ndim == 3:
        pred = pred[0]
    if pred.shape[0] < pred.shape[1]:
        pred = pred.T                       # → (N, 4+C)

    scores  = pred[:, 4:].max(axis=1)
    cls_ids = pred[:, 4:].argmax(axis=1)

    # Filter by confidence AND allowed class ids
    allowed = np.array(allowed_ids, dtype=np.int32)
    mask = (scores > conf_thr) & np.isin(cls_ids, allowed)
    if not mask.any():
        return np.empty((0, 6), dtype=np.float32)

    boxes   = pred[mask, :4]
    scores  = scores[mask]
    cls_ids = cls_ids[mask]

    # xywh → xyxy
    xyxy      = np.empty_like(boxes)
    xyxy[:,0] = boxes[:,0] - boxes[:,2] / 2
    xyxy[:,1] = boxes[:,1] - boxes[:,3] / 2
    xyxy[:,2] = boxes[:,0] + boxes[:,2] / 2
    xyxy[:,3] = boxes[:,1] + boxes[:,3] / 2

    idx = cv2.dnn.NMSBoxes(xyxy.tolist(), scores.tolist(), conf_thr, iou_thr)
    if len(idx) == 0:
        return np.empty((0, 6), dtype=np.float32)
    idx = np.asarray(idx).flatten()
    return np.concatenate([xyxy[idx],
                           scores[idx, None],
                           cls_ids[idx, None].astype(np.float32)], axis=1)


# ─────────────────────────────────────────────────────────────────────────────
# Detection result dataclass
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float
    cls_id: int
    cls_name: str
    cx: int           # bounding box centroid x (pixel)
    cy: int           # bounding box centroid y (pixel)
    bbox_h: int       # height in pixels (for fallback depth)


# ─────────────────────────────────────────────────────────────────────────────
# Public Detector class
# ─────────────────────────────────────────────────────────────────────────────
class Detector:
    """
    YOLOv8s TensorRT detector.

    Parameters
    ----------
    model_path : str
        Path to the .onnx file.
    cfg : dict
        Inference section from config.yaml.
    """

    def __init__(self, model_path: str, cfg: dict):
        self.use_color    = cfg.get("use_color", False)
        self.conf_thr     = cfg.get("conf_threshold", 0.50)
        self.iou_thr      = cfg.get("iou_threshold",  0.60)
        self.allowed_ids  = cfg.get("allowed_class_ids",
                                    [39, 41, 65, 67, 73, 76, 79])
        self._engine      = _ONNXEngine(model_path)
        self._frame_h     = cfg.get("input_size", 640)
        log.info(f"Detector loaded: {model_path} | color={self.use_color}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run inference on a single frame.

        Parameters
        ----------
        frame : np.ndarray
            BGR or grayscale frame from StereoCam (left camera).

        Returns
        -------
        List[Detection]  — sorted by confidence descending.
        """
        # Guard: reject empty / corrupt frames (e.g. dropped JPEG over network)
        if frame is None or frame.size == 0 or 0 in frame.shape:
            log.warning("detect() received an empty/corrupt frame — skipping.")
            return []

        fh, fw = frame.shape[:2]

        tensor, ratio, pad = _preprocess(frame, self.use_color)

        # Guard: ratio=0 would cause divide-by-zero → inf → OverflowError
        if not np.isfinite(ratio) or ratio == 0.0:
            log.warning(f"detect() got invalid scale ratio={ratio} — skipping frame.")
            return []

        raw  = self._engine.infer(tensor)
        dets = _nms(raw, self.conf_thr, self.iou_thr, self.allowed_ids)

        results = []
        for x1, y1, x2, y2, conf, cid in dets:
            # Un-pad & un-scale back to original frame coordinates
            # Use np.clip to keep coords finite before int-casting
            x1u = int(np.clip((x1 - pad[0]) / ratio, 0, fw - 1))
            y1u = int(np.clip((y1 - pad[1]) / ratio, 0, fh - 1))
            x2u = int(np.clip((x2 - pad[0]) / ratio, 0, fw - 1))
            y2u = int(np.clip((y2 - pad[1]) / ratio, 0, fh - 1))
            cid = int(cid)
            results.append(Detection(
                x1=x1u, y1=y1u, x2=x2u, y2=y2u,
                conf=float(conf),
                cls_id=cid,
                cls_name=COCO_NAMES[cid] if cid < len(COCO_NAMES) else str(cid),
                cx=(x1u + x2u) // 2,
                cy=(y1u + y2u) // 2,
                bbox_h=y2u - y1u,
            ))

        # Sort by confidence descending (best pick target first)
        results.sort(key=lambda d: d.conf, reverse=True)
        return results

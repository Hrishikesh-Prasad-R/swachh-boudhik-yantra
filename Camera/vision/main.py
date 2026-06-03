"""
main.py — Swachh Boudhik Yantra MVP Pipeline
Capture → Detect → Depth → Serial → Display

Controls:
    q / ESC  — quit
    c        — toggle color / BW inference mode
    d        — show/hide depth overlay
    s        — force send current target now (debug)
"""

import logging
import os
import sys
import time
from collections import deque

import cv2
import numpy as np
import yaml

# ── Module imports ─────────────────────────────────────────────────────────────
from camera      import StereoCam
from detector    import Detector, Detection
from depth       import StereoDepth
from serial_comm import ArduinoSerial

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────
def load_config(path: str = "config.yaml") -> dict:
    if not os.path.isfile(path):
        log.error(f"config.yaml not found at {path}")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────
BOX_COLOR  = (0, 255, 80)    # green — override from config below
TEXT_COLOR = (255, 255, 255)
FONT       = cv2.FONT_HERSHEY_SIMPLEX

def _draw_detection(
    frame: np.ndarray,
    det: Detection,
    X, Y, Z,
    is_target: bool,
    show_depth: bool,
    box_color,
) -> None:
    color  = (0, 80, 255) if is_target else box_color  # red for best target
    x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
    label  = f"{det.cls_name} {det.conf:.0%}"
    if show_depth and Z is not None:
        label += f"  Z={Z:.1f}cm"

    # Box
    thick = 3 if is_target else 2
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thick)
    # Centroid dot
    cv2.circle(frame, (det.cx, det.cy), 5, color, -1)
    # Label background
    (tw, th), _ = cv2.getTextSize(label, FONT, 0.55, 1)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 4),
                FONT, 0.55, TEXT_COLOR, 1, cv2.LINE_AA)


def _draw_hud(
    frame: np.ndarray,
    fps: float,
    lat_ms: float,
    color_mode: bool,
    serial_ok: bool,
    depth_ready: bool,
    last_cmd: str,
) -> None:
    h, w = frame.shape[:2]
    # Top-left HUD
    lines = [
        f"FPS: {fps:.1f}  Lat: {lat_ms:.1f}ms",
        f"Mode: {'COLOR' if color_mode else 'BW'}  Depth: {'calib' if depth_ready else 'fallback'}",
        f"Serial: {'OK' if serial_ok else 'disconnected'}",
    ]
    if last_cmd:
        lines.append(f"Sent: {last_cmd}")

    for i, line in enumerate(lines):
        y = 28 + i * 22
        cv2.putText(frame, line, (10, y), FONT, 0.55,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (10, y), FONT, 0.55,
                    (0, 255, 80), 1, cv2.LINE_AA)

    # Controls hint — bottom left
    hint = "q=quit  c=toggle-color  d=depth  s=force-send"
    cv2.putText(frame, hint, (10, h - 10), FONT, 0.42,
                (180, 180, 180), 1, cv2.LINE_AA)


def _to_display(frame: np.ndarray) -> np.ndarray:
    """Ensure frame is BGR for imshow, regardless of BW/color input."""
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# Stability tracker — require N consecutive detections of same class
# ─────────────────────────────────────────────────────────────────────────────
class StabilityTracker:
    def __init__(self, required_frames: int):
        self.required = required_frames
        self._history: deque = deque(maxlen=required_frames)

    def update(self, cls_name: str | None) -> bool:
        """Returns True when the same class has been seen for required_frames."""
        self._history.append(cls_name)
        if len(self._history) < self.required:
            return False
        return all(c == cls_name for c in self._history) and cls_name is not None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    cfg = load_config("config.yaml")
    inf_cfg    = cfg["inference"]
    cam_cfg    = cfg["camera"]
    depth_cfg  = cfg["depth"]
    serial_cfg = cfg["serial"]
    disp_cfg   = cfg["display"]

    box_color  = tuple(disp_cfg.get("box_color",  [0, 255, 80]))
    use_color  = inf_cfg.get("use_color", False)
    show_depth = disp_cfg.get("show_depth", True)

    # ── Camera ────────────────────────────────────────────────────────────
    log.info("Initialising stereo camera...")
    cam = StereoCam(cam_cfg, use_color=use_color)

    # ── Detector ──────────────────────────────────────────────────────────
    model_path = inf_cfg["onnx_path"]
    if not os.path.isfile(model_path):
        log.error(f"Model not found: {model_path}")
        cam.release()
        sys.exit(1)

    log.info(f"Loading detector: {model_path}")
    detector = Detector(model_path, inf_cfg)

    # ── Depth ─────────────────────────────────────────────────────────────
    log.info("Initialising depth estimator...")
    depth_est = StereoDepth(depth_cfg.get("calib_file"), depth_cfg)

    # ── Serial ────────────────────────────────────────────────────────────
    arduino = ArduinoSerial(serial_cfg)
    serial_ok = arduino.connect()
    if not serial_ok:
        log.warning("Running in display-only mode (no Arduino).")

    # ── Stability tracker ─────────────────────────────────────────────────
    tracker   = StabilityTracker(serial_cfg.get("stable_frames", 2))
    min_conf  = serial_cfg.get("min_conf_to_send", 0.55)
    frame_skip = inf_cfg.get("frame_skip", 1)

    # ── State ─────────────────────────────────────────────────────────────
    fps_dq     = deque(maxlen=60)
    last_dets  = []
    last_cmd   = ""
    fc         = 0
    last_X = last_Y = last_Z = None

    log.info(f"Starting — window: {disp_cfg['window_name']}")
    cv2.namedWindow(disp_cfg["window_name"], cv2.WINDOW_NORMAL)

    try:
        while True:
            t0 = time.perf_counter()

            left, right = cam.read()
            if left is None:
                log.warning("No frame — retrying...")
                time.sleep(0.05)
                continue

            fc += 1

            # ── Inference (every frame_skip frames) ───────────────────────
            if fc % frame_skip == 0:
                last_dets = detector.detect(left)

                # Depth for best detection
                last_X = last_Y = last_Z = None
                if last_dets:
                    best = last_dets[0]
                    if depth_est.ready:
                        left_gray, right_gray = cam.read_gray()
                        if left_gray is not None:
                            last_X, last_Y, last_Z = depth_est.compute(
                                left_gray, right_gray, best.cx, best.cy)
                    if last_Z is None:
                        last_Z = depth_est.fallback_depth(best.bbox_h)

                # ── Serial ────────────────────────────────────────────────
                target_cls = last_dets[0].cls_name if last_dets else None
                stable = tracker.update(target_cls)

                if last_dets and stable and last_dets[0].conf >= min_conf:
                    best = last_dets[0]
                    sent = arduino.send_pick(
                        best.cls_name, last_X, last_Y, last_Z, best.conf)
                    last_cmd = (
                        f"PICK {best.cls_name} "
                        f"({last_X},{last_Y},{last_Z}) "
                        f"{'✓' if sent else '✗'}"
                    )
                elif stable is False and not last_dets:
                    # Only send NO_TARGET once when transitioning to empty
                    pass  # avoid flooding with NO_TARGET every frame

            # ── Display ───────────────────────────────────────────────────
            display = _to_display(left.copy())

            for i, det in enumerate(last_dets):
                _draw_detection(
                    display, det,
                    last_X if i == 0 else None,
                    last_Y if i == 0 else None,
                    last_Z if i == 0 else None,
                    is_target=(i == 0),
                    show_depth=show_depth,
                    box_color=box_color,
                )

            elapsed = time.perf_counter() - t0
            fps = 1.0 / max(elapsed, 1e-6)
            fps_dq.append(fps)

            _draw_hud(
                display,
                fps=float(np.mean(fps_dq)),
                lat_ms=elapsed * 1000,
                color_mode=use_color,
                serial_ok=serial_ok,
                depth_ready=depth_est.ready,
                last_cmd=last_cmd,
            )

            cv2.imshow(disp_cfg["window_name"], display)

            # ── Key handling ──────────────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):          # q or ESC
                log.info("Quit requested.")
                break
            elif key == ord("c"):              # toggle BW/color
                use_color = not use_color
                detector.use_color = use_color
                log.info(f"Inference mode: {'COLOR' if use_color else 'BW'}")
            elif key == ord("d"):
                show_depth = not show_depth
            elif key == ord("s") and last_dets:  # force send
                best = last_dets[0]
                arduino.send_pick(best.cls_name, last_X, last_Y, last_Z, best.conf)
                last_cmd = f"FORCED PICK {best.cls_name}"

    finally:
        cam.release()
        arduino.disconnect()
        cv2.destroyAllWindows()
        log.info("Shutdown complete.")


if __name__ == "__main__":
    main()

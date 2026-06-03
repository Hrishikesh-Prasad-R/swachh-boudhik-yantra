"""
test_cameras.py — Quick camera smoke test (no TRT required)
Verifies both C270s open, captures frames, shows a live preview.
Press q to quit.
"""

import sys
import cv2
import yaml
import subprocess

def apply_v4l2(dev, exposure=151, brightness=108, gain=34):
    for ctrl, val in [
        ("auto_exposure", 1),
        ("exposure_time_absolute", exposure),
        ("brightness", brightness),
        ("gain", gain),
        ("white_balance_automatic", 0),
        ("power_line_frequency", 1),
    ]:
        subprocess.run(["v4l2-ctl", "-d", dev, f"--set-ctrl={ctrl}={val}"],
                       capture_output=True)

def main():
    cfg = yaml.safe_load(open("config.yaml"))
    cam_cfg = cfg["camera"]
    left_id  = cam_cfg.get("left_device",  0)
    right_id = cam_cfg.get("right_device", 2)
    w, h  = cam_cfg["width"], cam_cfg["height"]

    print(f"Testing LEFT  → /dev/video{left_id}")
    print(f"Testing RIGHT → /dev/video{right_id}")

    apply_v4l2(f"/dev/video{left_id}")
    apply_v4l2(f"/dev/video{right_id}")

    left  = cv2.VideoCapture(left_id,  cv2.CAP_V4L2)
    right = cv2.VideoCapture(right_id, cv2.CAP_V4L2)

    for cap, name in [(left, "LEFT"), (right, "RIGHT")]:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        if not cap.isOpened():
            print(f"✗ {name} camera FAILED to open!")
            sys.exit(1)
        print(f"✓ {name} camera opened")

    print("\nShowing stereo preview — press Q to quit\n")

    while True:
        ok_l, lf = left.read()
        ok_r, rf = right.read()

        if not ok_l or not ok_r:
            print("Frame read failed — retrying...")
            continue

        lg = cv2.cvtColor(lf, cv2.COLOR_BGR2GRAY)
        rg = cv2.cvtColor(rf, cv2.COLOR_BGR2GRAY)

        # Side-by-side
        side = cv2.hconcat([lg, rg])
        cv2.putText(side, "LEFT", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2)
        cv2.putText(side, "RIGHT", (w + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2)
        cv2.imshow("Stereo Camera Test — Q to quit", side)

        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    left.release()
    right.release()
    cv2.destroyAllWindows()
    print("Camera test done.")

if __name__ == "__main__":
    main()

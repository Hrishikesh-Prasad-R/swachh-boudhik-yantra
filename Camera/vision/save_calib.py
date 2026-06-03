#!/usr/bin/env bash
# save_calib.py wrapper — called by calib.sh after calibration
# Extracts /tmp/calibrationdata.tar.gz → parses left/right YAML → saves calib/stereo_calib.npz
#
# Also works standalone:
#   python3 save_calib.py
#   python3 save_calib.py --tarball /tmp/calibrationdata.tar.gz --out calib/stereo_calib.npz

"""
save_calib.py — Convert ROS stereo calibration output to stereo_calib.npz
"""

import argparse
import os
import sys
import tarfile
import tempfile

import numpy as np
import yaml


def _parse_ros_yaml(text: str) -> dict:
    """Parse a ROS camera_calibration YAML string into a flat dict of numpy arrays."""
    data = yaml.safe_load(text)
    rows = data["image_height"]
    cols = data["image_width"]

    def mat(key, r, c):
        return np.array(data[key]["data"], dtype=np.float64).reshape(r, c)

    return {
        "img_size": np.array([cols, rows], dtype=np.int32),
        "K":  mat("camera_matrix",          3, 3),
        "D":  mat("distortion_coefficients", 1, 5),
        "R":  mat("rectification_matrix",    3, 3),
        "P":  mat("projection_matrix",       3, 4),
    }


def convert(tarball_path: str, out_path: str) -> None:
    if not os.path.isfile(tarball_path):
        print(f"ERROR: Calibration tarball not found: {tarball_path}")
        print("  → Run stereo calibration first (./calib.sh), then hit CALIBRATE + SAVE.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Extracting {tarball_path} ...")
        with tarfile.open(tarball_path, "r:gz") as tf:
            tf.extractall(tmp)

        # ROS saves: left.yaml, right.yaml inside calibrationdata/
        left_yaml  = None
        right_yaml = None
        for root, _, files in os.walk(tmp):
            for fn in files:
                if fn == "left.yaml":
                    left_yaml  = open(os.path.join(root, fn)).read()
                elif fn == "right.yaml":
                    right_yaml = open(os.path.join(root, fn)).read()

        if left_yaml is None or right_yaml is None:
            print("ERROR: left.yaml or right.yaml not found in calibration tarball.")
            print(f"  Contents: {os.listdir(tmp)}")
            sys.exit(1)

    left  = _parse_ros_yaml(left_yaml)
    right = _parse_ros_yaml(right_yaml)

    # Compute derived quantities
    baseline = abs(right["P"][0, 3]) / left["P"][0, 0]
    focal    = left["P"][0, 0]
    cx0      = left["P"][0, 2]
    cy0      = left["P"][1, 2]
    w, h     = int(left["img_size"][0]), int(left["img_size"][1])

    calib_dir = os.path.dirname(out_path) or "."
    os.makedirs(calib_dir, exist_ok=True)

    # ── 1. Save binary .npz (used by depth.py) — always overwritten ────────
    np.savez(
        out_path,
        K1       = left["K"],
        D1       = left["D"],
        R1       = left["R"],
        P1       = left["P"],
        K2       = right["K"],
        D2       = right["D"],
        R2       = right["R"],
        P2       = right["P"],
        img_size = left["img_size"],
    )

    # ── 2. Save human-readable YAML — always overwritten ───────────────────
    from datetime import datetime

    def mat_to_list(m):
        return [round(float(v), 6) for v in m.flatten()]

    txt_path = os.path.join(calib_dir, "calibration_values.yaml")
    content  = f"""\
# Stereo Calibration Values
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Source: {tarball_path}
# Overwritten each time calib.sh is run.

image_size:
  width:  {w}
  height: {h}

derived:
  focal_px:       {focal:.4f}      # fx from left P matrix
  baseline:       {baseline:.6f}   # units = same as T (usually metres from ROS)
  cx0:            {cx0:.4f}        # principal point x (left)
  cy0:            {cy0:.4f}        # principal point y (left)
  depth_formula:  "Z = focal * baseline / disparity"

left_camera:
  K1:  {mat_to_list(left['K'])}    # 3x3 intrinsic matrix (row-major)
  D1:  {mat_to_list(left['D'])}    # distortion [k1,k2,p1,p2,k3]
  R1:  {mat_to_list(left['R'])}    # 3x3 rectification matrix
  P1:  {mat_to_list(left['P'])}    # 3x4 projection matrix

right_camera:
  K2:  {mat_to_list(right['K'])}
  D2:  {mat_to_list(right['D'])}
  R2:  {mat_to_list(right['R'])}
  P2:  {mat_to_list(right['P'])}
"""
    with open(txt_path, "w") as f:
        f.write(content)

    print(f"\n✅ Calibration saved:")
    print(f"   Binary  → {out_path}")
    print(f"   Readable→ {txt_path}")
    print(f"\n   Image size : {w}×{h}")
    print(f"   Focal (fx) : {focal:.2f} px")
    print(f"   Baseline   : {baseline:.6f}  (verify units — ROS T is in metres)")
    print(f"   cx0 / cy0  : {cx0:.1f} / {cy0:.1f}")
    print(f"\n   Depth formula:  Z = {focal:.1f} × {baseline:.4f} / disparity")
    print(f"   (Re-run calib.sh any time to overwrite both files)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert ROS stereo calib → stereo_calib.npz")
    parser.add_argument("--tarball", default="/tmp/calibrationdata.tar.gz",
                        help="Path to ROS calibration tarball (default: /tmp/calibrationdata.tar.gz)")
    parser.add_argument("--out", default="calib/stereo_calib.npz",
                        help="Output .npz path (default: calib/stereo_calib.npz)")
    args = parser.parse_args()
    convert(args.tarball, args.out)

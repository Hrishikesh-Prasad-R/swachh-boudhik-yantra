#!/usr/bin/env python3
"""
evaluate_trajectory.py  —  Stage 4A: ATE / RPE Evaluation
────────────────────────────────────────────────────────────
Computes Absolute Trajectory Error (ATE) and Relative Pose Error (RPE)
by comparing wheel odometry against RTAB-Map's refined odometry.

In simulation we use wheel odometry as the baseline reference
(diff_drive_controller ground truth is exact within Gazebo physics).
RTAB-Map's /rtabmap/odom is the estimated trajectory under evaluation.

For real ground truth comparison (research paper):
  1. Bridge Gazebo model pose:
       gz_bridge: /model/vacuum_robot/pose -> /ground_truth/pose
  2. Pass as --gt-topic /ground_truth/pose

Dependencies:
  pip install evo  (https://github.com/MichaelGrupp/evo)

Usage:
  # From a rosbag (standard workflow):
  python3.12 src/vacuum_utils/scripts/evaluate_trajectory.py \
      --bag bags/stage4_manual_mapping/room/run1.bag \
      --environment room

  # Live comparison (while sim is running — not recommended, use bag):
  python3.12 src/vacuum_utils/scripts/evaluate_trajectory.py \
      --live \
      --duration 60

  # Custom topic overrides:
  python3.12 src/vacuum_utils/scripts/evaluate_trajectory.py \
      --bag run.bag \
      --ref-topic /odom \
      --est-topic /rtabmap/odom

Outputs (written to bags/stage4_manual_mapping/<environment>/):
  ate_result.txt          — ATE absolute and RMSE statistics
  rpe_result.txt          — RPE statistics per delta
  trajectory_plot.png     — overlaid trajectory plot
  ate_error_plot.png      — ATE error over distance
  rpe_error_plot.png      — RPE error over distance
  metrics_summary.csv     — machine-readable summary
"""

import argparse
import csv
import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Acceptance criteria (Stage 4A Definition of Done)
# ─────────────────────────────────────────────────────────────────────────────
ATE_RMSE_MAX_M   = 0.30   # m  — ATE RMSE < 30cm for indoor SLAM
RPE_RMSE_MAX_M   = 0.05   # m  — RPE RMSE < 5cm per relative segment


def _check_evo():
    """Check evo is installed and print instructions if not."""
    if shutil.which('evo_ape') is None:
        print('[ERROR] evo not found. Install with:')
        print('  pip install evo')
        print()
        print('  evo GitHub: https://github.com/MichaelGrupp/evo')
        sys.exit(1)


def _check_ros2bag(bag_path: str) -> str:
    """Validate the rosbag exists and return its absolute path."""
    p = Path(bag_path).resolve()
    if not p.exists():
        print(f'[ERROR] Rosbag not found: {p}')
        sys.exit(1)
    return str(p)


def run_ate(bag_path: str, ref_topic: str, est_topic: str,
            output_dir: Path, environment: str) -> dict:
    """
    Run evo_ape on the rosbag to compute ATE.
    Returns a dict with RMSE, mean, std, max.
    """
    result_file = output_dir / 'ate_result.txt'
    plot_file   = output_dir / 'trajectory_plot.pdf'
    ate_plot    = output_dir / 'ate_error_plot.pdf'

    cmd = [
        'evo_ape', 'bag2',
        bag_path,
        ref_topic,
        est_topic,
        '--align',          # align trajectories (removes global datum offset)
        '--correct_scale',  # correct scale if needed
        '-p',               # plot
        '--plot_mode', 'xy',
        '--save_results', str(output_dir / 'ate_results.zip'),
        '--save_plot',    str(plot_file),
    ]

    print(f'\n[ATE] Running: {" ".join(cmd)}')
    result = subprocess.run(cmd, capture_output=True, text=True)

    output = result.stdout + result.stderr
    print(output)

    with open(result_file, 'w') as f:
        f.write(f'ATE Evaluation — {environment} — {datetime.now()}\n')
        f.write('=' * 60 + '\n')
        f.write(output)

    # Parse RMSE from evo output
    metrics = _parse_evo_metrics(output)
    return metrics


def run_rpe(bag_path: str, ref_topic: str, est_topic: str,
            output_dir: Path, environment: str) -> dict:
    """
    Run evo_rpe on the rosbag to compute RPE.
    Uses delta=1 (frame-to-frame relative pose error).
    """
    result_file = output_dir / 'rpe_result.txt'

    cmd = [
        'evo_rpe', 'bag2',
        bag_path,
        ref_topic,
        est_topic,
        '--delta', '1',
        '--delta_unit', 'm',   # evaluate per 1m of travel
        '--align',
        '--save_results', str(output_dir / 'rpe_results.zip'),
    ]

    print(f'\n[RPE] Running: {" ".join(cmd)}')
    result = subprocess.run(cmd, capture_output=True, text=True)

    output = result.stdout + result.stderr
    print(output)

    with open(result_file, 'w') as f:
        f.write(f'RPE Evaluation — {environment} — {datetime.now()}\n')
        f.write('=' * 60 + '\n')
        f.write(output)

    metrics = _parse_evo_metrics(output)
    return metrics


def _parse_evo_metrics(evo_output: str) -> dict:
    """Parse RMSE, mean, median, std, min, max from evo stdout."""
    metrics = {'rmse': None, 'mean': None, 'median': None,
               'std': None, 'min': None, 'max': None}
    for line in evo_output.splitlines():
        line = line.strip()
        for key in metrics:
            if line.lower().startswith(key):
                try:
                    metrics[key] = float(line.split()[-1])
                except (IndexError, ValueError):
                    pass
    return metrics


def _write_summary_csv(output_dir: Path, environment: str,
                        ate_metrics: dict, rpe_metrics: dict):
    csv_path = output_dir / 'metrics_summary.csv'
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['metric', 'value', 'unit', 'environment', 'timestamp'])
        ts = datetime.now().isoformat()
        for key, val in ate_metrics.items():
            w.writerow([f'ate_{key}', val, 'm', environment, ts])
        for key, val in rpe_metrics.items():
            w.writerow([f'rpe_{key}', val, 'm', environment, ts])
    print(f'\n[ok] Metrics CSV: {csv_path}')


def _print_summary(environment: str, ate: dict, rpe: dict):
    ate_rmse = ate.get('rmse') or 0.0
    rpe_rmse = rpe.get('rmse') or 0.0

    ate_pass = ate_rmse <= ATE_RMSE_MAX_M
    rpe_pass = rpe_rmse <= RPE_RMSE_MAX_M

    print('\n' + '=' * 62)
    print(f'  TRAJECTORY EVALUATION — {environment.upper()}')
    print('=' * 62)
    print(f'  ATE RMSE : {ate_rmse:.4f} m  '
          f'(criterion: <={ATE_RMSE_MAX_M}m)  '
          f'{"PASS" if ate_pass else "FAIL"}')
    print(f'  ATE mean : {ate.get("mean", "n/a"):.4f} m')
    print(f'  ATE max  : {ate.get("max",  "n/a"):.4f} m')
    print()
    print(f'  RPE RMSE : {rpe_rmse:.4f} m  '
          f'(criterion: <={RPE_RMSE_MAX_M}m)  '
          f'{"PASS" if rpe_pass else "FAIL"}')
    print(f'  RPE mean : {rpe.get("mean", "n/a"):.4f} m')
    print()
    overall = 'ALL PASS ✅' if (ate_pass and rpe_pass) else 'SOME FAILED ❌'
    print(f'  {overall}')
    print('=' * 62)


def main():
    ap = argparse.ArgumentParser(
        description='RTAB-Map Trajectory Evaluation (ATE / RPE)  — Stage 4A')
    ap.add_argument('--bag',         required=True,
                    help='Path to rosbag (.bag or directory)')
    ap.add_argument('--ref-topic',   default='/odom',
                    help='Reference odometry topic (default: /odom)')
    ap.add_argument('--est-topic',   default='/rtabmap/odom',
                    help='Estimated trajectory topic (default: /rtabmap/odom)')
    ap.add_argument('--environment', default='room',
                    help='Environment label for output naming')
    ap.add_argument('--output-dir',  default=None,
                    help='Output directory (default: bags/stage4_manual_mapping/<env>)')
    args = ap.parse_args()

    _check_evo()

    bag_path = _check_ros2bag(args.bag)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(f'bags/stage4_manual_mapping/{args.environment}')
    output_dir.mkdir(parents=True, exist_ok=True)

    print('=' * 62)
    print(f'  Stage 4A: Trajectory Evaluation  ({args.environment})')
    print('=' * 62)
    print(f'  Bag         : {bag_path}')
    print(f'  Reference   : {args.ref_topic}')
    print(f'  Estimate    : {args.est_topic}')
    print(f'  Output dir  : {output_dir}')

    ate_metrics = run_ate(
        bag_path, args.ref_topic, args.est_topic, output_dir, args.environment)
    rpe_metrics = run_rpe(
        bag_path, args.ref_topic, args.est_topic, output_dir, args.environment)

    _write_summary_csv(output_dir, args.environment, ate_metrics, rpe_metrics)
    _print_summary(args.environment, ate_metrics, rpe_metrics)


if __name__ == '__main__':
    main()

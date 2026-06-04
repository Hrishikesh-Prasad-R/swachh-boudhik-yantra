# Swachh Boudhik Yantra — Benchmark Metrics

This folder contains per-frame performance measurements collected from the
distributed robotic vision pipeline (RPi 5 → Gigabit Ethernet → RTX A6000).

## Files

| File | Frames | Description |
|---|---|---|
| `benchmark_20260604_170808.csv` | 1,157 | **Primary run** — 120 s @ 10 FPS, 100% PDR |
| `benchmark_20260604_170808.summary.json` | — | Aggregate statistics for primary run |
| `benchmark_20260604_170435.csv` | 382 | Aborted trial run (topology fix in progress) |
| `benchmark_20260604_170435.summary.json` | — | Summary for trial run |

## Primary Run Highlights (2026-06-04)

| Metric | Value |
|---|---|
| Duration | 120 s |
| Effective FPS | 9.64 |
| Packet Delivery Ratio | **100.00%** |
| Round-Trip Latency (mean ± std) | **50.98 ± 4.64 ms** |
| GPU Inference — YOLOv8s (mean ± std) | **50.59 ± 3.69 ms** |
| P99 Round-Trip | 61.1 ms |
| Network Bandwidth | 2.15 Mbps / 1000 Mbps available |
| GPU Utilisation | 5% |
| GPU Temperature | 43 °C |

## CSV Column Reference

| Column | Unit | Description |
|---|---|---|
| `frame_id` | — | Sequential frame index |
| `wall_clock_utc` | ISO 8601 | Send timestamp |
| `round_trip_ms` | ms | Full pipeline latency |
| `network_one_way_ms` | ms | Transport latency estimate |
| `det_ms` | ms | YOLOv8s GPU inference time |
| `num_detections` | count | Objects detected |
| `total_payload_bytes` | bytes | ZMQ message size (stereo JPEG pair) |
| `throughput_mbps` | Mbps | Instantaneous bandwidth |
| `det0_*` | — | Primary detection bounding box + 3D coords |
| `gpu_util_pct` | % | GPU utilisation (nvidia-smi) |
| `gpu_mem_used_mb` | MiB | GPU memory used |
| `gpu_temp_c` | °C | GPU die temperature |
| `cpu_util_pct` | % | CPU utilisation |
| `ram_used_mb` | MiB | System RAM used |
| `result_timeout` | 0/1 | 1 = no result received for frame |

## Reproducing

```bash
# On Windows GPU system (gpu_worker.py must be running with --rpi-host 127.0.0.1):
python Camera/network/journal_benchmark.py --duration 120 --fps 10
```

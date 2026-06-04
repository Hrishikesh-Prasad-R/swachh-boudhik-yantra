# Camera/network — Distributed Processing Transport Layer

This directory implements the wireless link between the **Raspberry Pi 5** (robot) and the **Windows 11 GPU System** (NVIDIA RTX A600) for the Swachh Boudhik Yantra autonomous cleaning robot.

## Architecture

```
RPi 5 (192.168.4.1 — Hotspot)         Windows 11 GPU System
─────────────────────────────          ──────────────────────────
rpi_publisher.py                       gpu_worker.py
  │                                      │
  │── ZMQ PUB :5555 ──── frames ────────►│
  │                                      │── YOLOv8 (CUDA)
  │◄─── ZMQ PUSH :5556 ── results ───────│── Stereo Depth
  │                                      │
  ▼                                      
serial_comm.py → Arduino               
```

**Transport:** ZMQ PUB/SUB (`pyzmq`) — no broker, ~2–5ms overhead, auto-reconnect.

---

## Directory Structure

```
network/
├── network_config.yaml          # Ports, JPEG quality, ZMQ tuning
├── rpi_publisher.py             # Runs on RPi — streams frames, receives results
├── gpu_worker.py                # Runs on GPU — detects, returns results
├── benchmark.py                 # Measures FPS, latency, bandwidth
│
├── rpi_setup/
│   ├── hotspot_setup.sh         # One-time: configure RPi as WiFi AP
│   ├── hotspot_stop.sh          # Restore RPi to WiFi client mode
│   └── sync_calib.sh            # Copy stereo_calib.npz to GPU system
│
└── gpu_setup/
    ├── setup_windows.ps1        # One-time: install deps, firewall rules
    └── check_cuda.py            # Verify CUDA + network before running
```

---

## Quick Start

### Step 1 — Set up the RPi Hotspot (run once on RPi)

```bash
sudo bash Camera/network/rpi_setup/hotspot_setup.sh
# SSID: swachh-bot  |  Password: swachh2024  |  RPi IP: 192.168.4.1
```

Reboot RPi. The hotspot will auto-start on boot.

---

### Step 2 — Set up the GPU System (run once on Windows, as Admin)

```powershell
# In PowerShell (Administrator):
cd C:\path\to\swachh-boudhik-yantra\Camera\network\gpu_setup
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_windows.ps1
```

Then connect the Windows machine to WiFi **`swachh-bot`** (password: `swachh2024`).

---

### Step 3 — Copy model file to GPU system

Copy `Camera/vision/models/yolov8s.onnx` from the RPi to the same path on the Windows machine. Use `scp`, a USB drive, or any file transfer method.

```bash
# From RPi (if OpenSSH Server is enabled on Windows):
scp Camera/vision/models/yolov8s.onnx <windows_user>@192.168.4.101:Desktop/swachh-boudhik-yantra/Camera/vision/models/
```

---

### Step 4 — Verify GPU + Network

```powershell
# On Windows, in the gpu_setup venv:
cd Camera\network\gpu_setup
.\swachh-gpu-env\Scripts\activate
python check_cuda.py
```

Expected output:
```
  ✓ CUDAExecutionProvider is ACTIVE — RTX A600 will be used!
  ✓ RPi reachable at 192.168.4.1
```

---

### Step 5 — Run the benchmark test

```bash
# On RPi:
cd Camera/network
source ../vision/venv/bin/activate
python benchmark.py --mode roundtrip --duration 30

# On GPU (Windows), start worker first:
cd Camera\network
python gpu_worker.py --no-depth   # use --no-depth if calib not synced yet
```

Expected results:
| Metric | Target |
|---|---|
| Round-trip latency | < 100ms |
| Effective FPS | ≥ 8 FPS |
| Bandwidth | ~5 Mbps |

---

### Step 6 — Run full distributed pipeline

```bash
# On GPU system (Windows) — start first:
python gpu_worker.py

# On RPi:
cd Camera/vision
python ../network/rpi_publisher.py --test   # --test skips Arduino
```

The RPi window will show live camera feed with detections sourced from the GPU.

---

## Optional: Sync Calibration File

If stereo calibration is done on the RPi, sync the file to the GPU system for accurate depth:

```bash
# On RPi, find GPU system IP first:
cat /var/lib/misc/dnsmasq.leases

# Then sync:
bash Camera/network/rpi_setup/sync_calib.sh 192.168.4.101
```

After syncing, run `gpu_worker.py` without `--no-depth`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| GPU can't connect to 192.168.4.1 | Check WiFi is connected to `swachh-bot`, not another network |
| `CUDAExecutionProvider` missing | Install CUDA Toolkit 11.8+ from nvidia.com, reinstall `onnxruntime-gpu` |
| Firewall blocking ZMQ | Re-run `setup_windows.ps1` as Admin, or manually allow ports 5555/5556 |
| Low FPS / high latency | Reduce `jpeg_quality` in `network_config.yaml` (try 50), or increase `frame_skip` |
| hotspot not starting on RPi | `sudo journalctl -u hostapd -n 30` to see errors |
| `ImportError: cannot import detector` | Run `gpu_worker.py` from `Camera/network/` directory |

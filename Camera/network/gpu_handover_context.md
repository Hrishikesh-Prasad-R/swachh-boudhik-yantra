# Swachh Boudhik Yantra — GPU System Handover Context
This document serves as a handover file for the Antigravity instance running on the Windows GPU system. It outlines the current state, network configuration, issues resolved, and immediate next steps.

---

## 1. System Architecture (Distributed Setup)
We are running a split processing pipeline:
- **Raspberry Pi 5 (RPi5):** Captures stereo video frames using 2x Logitech C270 cameras, encodes them to JPEG, streams them via ZMQ (`PUB`), receives object detection coordinates back via ZMQ (`PULL`), and controls the Arduino arm.
- **Windows GPU PC (NVIDIA RTX A600):** Subscribes to the frame stream, executes high-speed YOLOv8s inference using ONNX Runtime with `CUDAExecutionProvider`, calculates stereo depth, and sends detection coordinates back to the RPi.

---

## 2. Network Configuration
To maintain stability and low latency, we configured a **direct Ethernet connection** between the two systems:
- **RPi 5 IP (eth0):** `10.0.0.1` (Static, configured via NetworkManager profile `eth0-static`)
- **Windows PC IP (Ethernet):** `10.0.0.2` (Static, Subnet: `255.255.255.0`, Gateway: `10.0.0.1`, DNS: `8.8.8.8`)
- **ZMQ Ports:** `5555` (Frame Stream PUB/SUB), `5556` (Detections PUSH/PULL)

### Internet Sharing (NAT)
Because the Windows PC has no built-in Wi-Fi and needs internet to download pip packages, we configured the RPi to share its Wi-Fi internet (`wlan0`) over the Ethernet cable (`eth0`):
- `net.ipv4.ip_forward = 1` is enabled on RPi.
- IPTables masquerades and forwards packets from `eth0` to `wlan0`.
- **Result:** The Windows PC currently has full internet access through the Ethernet connection using the RPi as its gateway.

---

## 3. Issues Faced & Resolved
1. **No GPU System WiFi:** We pivoted from a wireless hotspot model to a direct ethernet link. This provides extremely low latency (~1ms ping) and high bandwidth (~1 Gbps).
2. **No PC Internet:** We enabled NAT on the RPi to forward its Wi-Fi internet connection to the PC via the Ethernet cable.
3. **PowerShell Script Parser Errors:** Copy-pasting the setup script caused encoding issues (corrupting characters like `_` and quotes). We resolved this by pushing the clean codebase to GitHub, allowing the PC to clone it directly.

---

## 4. Current Codebase State
The repository has been successfully pushed to GitHub and cloned onto the Windows system at:
`C:\Users\BMSCECSE\Desktop\swachh-boudhik-yantra\`

**Key Network files:**
- `Camera/network/network_config.yaml`: Contains configuration parameters (ZMQ endpoints set to `10.0.0.1`).
- `Camera/network/gpu_worker.py`: The worker script to run on the GPU system.
- `Camera/network/gpu_setup/setup_windows.ps1`: The environment configuration script.
- `Camera/network/gpu_setup/check_cuda.py`: Validation script for CUDA and network.
- `Camera/network/benchmark.py`: Network performance benchmark script.

---

## 5. Immediate Next Steps for Windows Antigravity
The Windows Antigravity instance should run the following commands in **Administrator PowerShell**:

1. **Run the Environment Setup Script:**
   ```powershell
   cd C:\Users\BMSCECSE\Desktop\swachh-boudhik-yantra\Camera\network\gpu_setup
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\setup_windows.ps1
   ```
   *This script will create `swachh-gpu-env` venv, run pip installations over our shared internet link, and add Windows firewall exceptions for ports 5555/5556.*

2. **Retrieve the Model File:**
   Copy the `yolov8s.onnx` file from the RPi to the Windows PC. 
   - Source: `/home/swachh/Desktop/swachh-boudhik-yantra/Camera/vision/models/yolov8s.onnx`
   - Destination: `C:\Users\BMSCECSE\Desktop\swachh-boudhik-yantra\Camera\vision\models\yolov8s.onnx`

3. **Verify the Environment:**
   ```powershell
   python check_cuda.py
   ```
   *Verify that `CUDAExecutionProvider` is active and the RPi is pingable.*

4. **Start testing:**
   Refer to `testing_checklist.md` in the workspace to run through Tests 1-6.

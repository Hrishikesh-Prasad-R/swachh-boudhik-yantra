"""
check_cuda.py — Swachh Boudhik Yantra
Quick CUDA and ONNX Runtime verification for the GPU system.

Run this on the Windows GPU machine BEFORE starting gpu_worker.py.
It confirms CUDA is accessible and reports GPU info.

Usage (Windows):
    python check_cuda.py
    # or via batch file:
    run_check_cuda.bat
"""

import sys


def check_python_version():
    v = sys.version_info
    ok = v.major >= 3 and v.minor >= 10
    status = "✓" if ok else "✗"
    print(f"  {status} Python: {v.major}.{v.minor}.{v.micro}"
          + ("" if ok else "  ← 3.10+ required"))
    return ok


def check_onnxruntime():
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        cuda_ok = "CUDAExecutionProvider" in providers

        print(f"\n  ONNX Runtime version: {ort.__version__}")
        print(f"  Available providers:")
        for p in providers:
            marker = "  ✓" if "CUDA" in p else "    "
            print(f"    {marker} {p}")

        if cuda_ok:
            print("\n  ✓ CUDAExecutionProvider is ACTIVE — RTX A600 will be used!")
        else:
            print("\n  ✗ CUDAExecutionProvider NOT available.")
            print("    → Install CUDA Toolkit: https://developer.nvidia.com/cuda-downloads")
            print("    → Make sure onnxruntime-gpu is installed (not plain onnxruntime)")

        return cuda_ok, ort.__version__

    except ImportError:
        print("  ✗ onnxruntime not installed.")
        print("    Run: pip install onnxruntime-gpu")
        return False, None


def check_cuda_toolkit():
    """Try to get CUDA version from nvidia-smi."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    print(f"\n  GPU Name:         {parts[0]}")
                    print(f"  VRAM:             {parts[1]}")
                    print(f"  Driver Version:   {parts[2]}")
                    print(f"  Compute Cap:      {parts[3]}")
            return True
        else:
            print("  ✗ nvidia-smi failed — NVIDIA driver may not be installed.")
            return False
    except FileNotFoundError:
        print("  ✗ nvidia-smi not found — NVIDIA driver not installed or not in PATH.")
        return False
    except Exception as e:
        print(f"  ✗ nvidia-smi error: {e}")
        return False


def check_zmq():
    try:
        import zmq
        print(f"  ✓ pyzmq: {zmq.__version__}")
        return True
    except ImportError:
        print("  ✗ pyzmq not installed. Run: pip install pyzmq")
        return False


def check_opencv():
    try:
        import cv2
        print(f"  ✓ OpenCV: {cv2.__version__}")
        return True
    except ImportError:
        print("  ✗ opencv-python not installed. Run: pip install opencv-python")
        return False


def check_numpy():
    try:
        import numpy as np
        print(f"  ✓ NumPy: {np.__version__}")
        return True
    except ImportError:
        print("  ✗ numpy not installed.")
        return False


def check_network(rpi_host="192.168.4.1"):
    """Try to ping the RPi hotspot IP."""
    import subprocess, platform
    ping_cmd = ["ping", "-n", "3", rpi_host] if platform.system() == "Windows" \
               else ["ping", "-c", "3", rpi_host]
    try:
        result = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Extract avg RTT from ping output
            for line in result.stdout.split("\n"):
                if "Average" in line or "avg" in line:
                    print(f"  ✓ RPi reachable at {rpi_host}")
                    print(f"    {line.strip()}")
                    return True
            print(f"  ✓ RPi reachable at {rpi_host}")
            return True
        else:
            print(f"  ✗ Cannot reach {rpi_host}")
            print("    → Are you connected to WiFi 'swachh-bot'?")
            return False
    except Exception as e:
        print(f"  ✗ Ping failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
def main():
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   Swachh Boudhik Yantra — GPU System Check          ║")
    print("╚══════════════════════════════════════════════════════╝")

    all_ok = True

    print("\n── Python ──────────────────────────────────────────────")
    all_ok &= check_python_version()

    print("\n── GPU / CUDA ──────────────────────────────────────────")
    gpu_ok = check_cuda_toolkit()
    all_ok &= gpu_ok

    print("\n── ONNX Runtime ────────────────────────────────────────")
    cuda_ok, ort_ver = check_onnxruntime()
    all_ok &= cuda_ok

    print("\n── Python Packages ─────────────────────────────────────")
    all_ok &= check_zmq()
    all_ok &= check_opencv()
    all_ok &= check_numpy()

    print("\n── Network (RPi Hotspot) ────────────────────────────────")
    net_ok = check_network("192.168.4.1")
    # Network is tested separately — not blocking

    print()
    if all_ok and net_ok:
        print("╔══════════════════════════════════════════════════════╗")
        print("║   ALL CHECKS PASSED ✓                               ║")
        print("║   Ready to run: python gpu_worker.py                ║")
        print("╚══════════════════════════════════════════════════════╝")
    elif all_ok and not net_ok:
        print("╔══════════════════════════════════════════════════════╗")
        print("║   GPU/CUDA OK ✓  — Network NOT connected yet        ║")
        print("║   Connect to WiFi 'swachh-bot' and re-run.          ║")
        print("╚══════════════════════════════════════════════════════╝")
    else:
        print("╔══════════════════════════════════════════════════════╗")
        print("║   SOME CHECKS FAILED ✗ — Fix issues above first     ║")
        print("╚══════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()

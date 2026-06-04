# setup_windows.ps1 — Swachh Boudhik Yantra GPU System Setup
# Run this on the Windows 11 GPU machine (as Administrator).
#
# What this does:
#   1. Checks Python 3.10+ is installed
#   2. Creates a Python venv in .\swachh-gpu-env\
#   3. Installs required packages (pyzmq, onnxruntime-gpu, opencv, etc.)
#   4. Verifies CUDA is accessible via onnxruntime
#   5. Adds Windows Firewall rules for ZMQ ports 5555 and 5556
#
# Usage (run in Windows PowerShell as Admin):
#   cd C:\path\to\swachh-boudhik-yantra\Camera\network\gpu_setup
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup_windows.ps1

$ErrorActionPreference = "Stop"

# ── Colour helpers ────────────────────────────────────────────────────────────
function Write-Info   { param($msg) Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-OK     { param($msg) Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Fail   { param($msg) Write-Host "[FAIL]  $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║   Swachh Boudhik Yantra — GPU System Setup (Win11)   ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ── Step 1: Check Python ──────────────────────────────────────────────────────
Write-Info "Checking Python installation..."
try {
    $pyVer = python --version 2>&1
    Write-OK "Found: $pyVer"
    # Extract version numbers
    $verMatch = $pyVer -match "Python (\d+)\.(\d+)"
    if ($verMatch) {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Fail "Python 3.10+ required. Download from https://python.org"
            exit 1
        }
        Write-OK "Python version OK ($major.$minor)"
    }
} catch {
    Write-Fail "Python not found. Download from: https://python.org/downloads/"
    Write-Info "Make sure 'Add Python to PATH' is checked during install."
    exit 1
}

# ── Step 2: Check pip ─────────────────────────────────────────────────────────
Write-Info "Checking pip..."
try {
    python -m pip --version | Out-Null
    Write-OK "pip available."
} catch {
    Write-Fail "pip not found. Run: python -m ensurepip"
    exit 1
}

# ── Step 3: Create virtual environment ────────────────────────────────────────
$VENV_DIR = ".\swachh-gpu-env"
Write-Info "Creating virtual environment at $VENV_DIR ..."
if (Test-Path $VENV_DIR) {
    Write-Warn "venv already exists — reusing it."
} else {
    python -m venv $VENV_DIR
    Write-OK "venv created."
}

$PY  = "$VENV_DIR\Scripts\python.exe"
$PIP = "$VENV_DIR\Scripts\pip.exe"

# ── Step 4: Upgrade pip ───────────────────────────────────────────────────────
Write-Info "Upgrading pip..."
& $PIP install --upgrade pip --quiet
Write-OK "pip upgraded."

# ── Step 5: Install packages ──────────────────────────────────────────────────
Write-Info "Installing required packages..."
Write-Info "(This may take a few minutes — onnxruntime-gpu is ~100MB)"

$PACKAGES = @(
    "pyzmq",
    "onnxruntime-gpu",       # CUDA-enabled ONNX runtime for RTX A600
    "opencv-python",
    "numpy",
    "pyyaml"
)

foreach ($pkg in $PACKAGES) {
    Write-Info "  Installing $pkg ..."
    & $PIP install $pkg --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-OK "  $pkg installed."
    } else {
        Write-Fail "  Failed to install $pkg"
        exit 1
    }
}

# ── Step 6: Verify CUDA via ONNX Runtime ─────────────────────────────────────
Write-Info "Verifying CUDA availability via ONNX Runtime..."
$cudaCheck = & $PY -c @"
import onnxruntime as ort
providers = ort.get_available_providers()
print('Providers:', providers)
if 'CUDAExecutionProvider' in providers:
    print('CUDA_OK')
else:
    print('CUDA_MISSING')
"@

Write-Info "  $cudaCheck"
if ($cudaCheck -match "CUDA_OK") {
    Write-OK "CUDA is available — RTX A600 will be used for inference!"
} else {
    Write-Warn "CUDA not detected by onnxruntime-gpu."
    Write-Warn "Make sure CUDA Toolkit 11.8 or 12.x is installed:"
    Write-Warn "  https://developer.nvidia.com/cuda-downloads"
    Write-Warn "Inference will still work on CPU, but slower."
}

# ── Step 7: Windows Firewall rules ────────────────────────────────────────────
Write-Info "Adding Windows Firewall rules for ZMQ ports 5555 and 5556..."

$fwRules = @(
    @{Name="Swachh-ZMQ-5555-In";  Port=5555; Dir="in"},
    @{Name="Swachh-ZMQ-5556-In";  Port=5556; Dir="in"},
    @{Name="Swachh-ZMQ-5555-Out"; Port=5555; Dir="out"},
    @{Name="Swachh-ZMQ-5556-Out"; Port=5556; Dir="out"}
)

foreach ($rule in $fwRules) {
    $existing = netsh advfirewall firewall show rule name=$rule.Name 2>&1
    if ($existing -match "No rules match") {
        netsh advfirewall firewall add rule `
            name=$rule.Name `
            dir=$rule.Dir `
            action=allow `
            protocol=TCP `
            localport=$rule.Port | Out-Null
        Write-OK "  Firewall rule added: $($rule.Name)"
    } else {
        Write-Warn "  Rule already exists: $($rule.Name)"
    }
}

# ── Step 8: Create launcher scripts ───────────────────────────────────────────
Write-Info "Creating launcher batch files..."

# gpu_worker launcher
$workerLauncher = @"
@echo off
REM Swachh Boudhik Yantra — GPU Worker Launcher
REM Run from the Camera\network directory
cd /d %~dp0..
call gpu_setup\swachh-gpu-env\Scripts\activate.bat
python gpu_worker.py %*
pause
"@
$workerLauncher | Out-File -FilePath "run_gpu_worker.bat" -Encoding ascii
Write-OK "  Created run_gpu_worker.bat"

# check_cuda launcher
$cudaLauncher = @"
@echo off
REM Swachh — Quick CUDA check
cd /d %~dp0
call swachh-gpu-env\Scripts\activate.bat
python check_cuda.py
pause
"@
$cudaLauncher | Out-File -FilePath "run_check_cuda.bat" -Encoding ascii
Write-OK "  Created run_check_cuda.bat"

# ── Step 9: Final summary ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   Setup Complete!                                    ║" -ForegroundColor Green
Write-Host "║                                                      ║" -ForegroundColor Green
Write-Host "║   Next steps:                                        ║" -ForegroundColor Green
Write-Host "║   1. Connect to WiFi SSID: swachh-bot               ║" -ForegroundColor Green
Write-Host "║   2. Copy yolov8s.onnx from RPi to:                 ║" -ForegroundColor Green
Write-Host "║      Camera\vision\models\yolov8s.onnx              ║" -ForegroundColor Green
Write-Host "║   3. Run check_cuda.py to verify GPU                 ║" -ForegroundColor Green
Write-Host "║   4. Run gpu_worker.py to start processing          ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Info "To activate the venv manually:"
Write-Info "  .\swachh-gpu-env\Scripts\Activate.ps1"
Write-Info "To run the worker:"
Write-Info "  python ..\gpu_worker.py"

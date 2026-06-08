# setup_ros2_windows.ps1 — Swachh Boudhik Yantra
# ROS 2 Humble + Navigation2 Full Setup for Windows 11 GPU System
#
# Run as Administrator in PowerShell:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup_ros2_windows.ps1
#
# Prerequisites: Internet connection (via RPi NAT forwarding or USB tether)

$ErrorActionPreference = "Stop"
$ROS2_VERSION  = "humble"
$ROS2_ZIP_URL  = "https://github.com/ros2/ros2/releases/download/release-humble-20250415/ros2-humble-20250415-windows-release-amd64.zip"
$ROS2_DIR      = "C:\dev\ros2_humble"
$ROS2_WS       = "C:\dev\ros2_ws"
$DOWNLOAD_DIR  = "$env:TEMP\ros2_setup"

# ── Colour + Progress Helpers ────────────────────────────────────────────────
function Write-Phase   { param($num, $total, $msg) Write-Host "`n═══════════════════════════════════════════════════════" -ForegroundColor DarkCyan; Write-Host "  Phase $num/$total — $msg" -ForegroundColor Cyan; Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor DarkCyan }
function Write-Step    { param($msg) Write-Host "  ⬜ $msg ..." -ForegroundColor White -NoNewline }
function Write-Done    { Write-Host "`r  ✅" -ForegroundColor Green -NoNewline; Write-Host " $args" -ForegroundColor Green }
function Write-Skip    { Write-Host "`r  ⏭️" -ForegroundColor Yellow -NoNewline; Write-Host " $args (already installed)" -ForegroundColor Yellow }
function Write-Fail    { Write-Host "`r  ❌" -ForegroundColor Red -NoNewline; Write-Host " $args" -ForegroundColor Red }
function Write-Info    { Write-Host "  ℹ️  $args" -ForegroundColor DarkGray }

# ── Admin Check ──────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "`n  ❌ This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "     Right-click PowerShell → Run as Administrator`n" -ForegroundColor Yellow
    exit 1
}

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║  Swachh Boudhik Yantra — ROS 2 Humble + Nav2 Setup       ║" -ForegroundColor Magenta
Write-Host "║  Target: Windows 11 / NVIDIA RTX A6000                   ║" -ForegroundColor Magenta
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

$totalPhases = 6
New-Item -ItemType Directory -Force -Path $DOWNLOAD_DIR | Out-Null

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 1: Chocolatey Package Manager
# ═════════════════════════════════════════════════════════════════════════════
Write-Phase 1 $totalPhases "Chocolatey Package Manager"

Write-Step "Checking Chocolatey"
$chocoInstalled = Get-Command choco -ErrorAction SilentlyContinue
if ($chocoInstalled) {
    Write-Done "Chocolatey $(choco --version)"
} else {
    Write-Host ""
    Write-Info "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Done "Chocolatey installed"
}

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 2: System Prerequisites
# ═════════════════════════════════════════════════════════════════════════════
Write-Phase 2 $totalPhases "System Prerequisites (via Chocolatey)"

$chocoPackages = @(
    @{Name="cmake";              DisplayName="CMake (Build System)"},
    @{Name="git";                DisplayName="Git"},
    @{Name="openssl";            DisplayName="OpenSSL (DDS Security)"},
    @{Name="vcredist140";        DisplayName="Visual C++ Redistributable 2015-2022"},
    @{Name="graphviz";           DisplayName="Graphviz (rqt graph tools)"},
    @{Name="wget";               DisplayName="wget (download utility)"}
)

foreach ($pkg in $chocoPackages) {
    Write-Step $pkg.DisplayName
    $installed = choco list --local-only --exact $pkg.Name 2>$null | Select-String $pkg.Name
    if ($installed) {
        Write-Skip $pkg.DisplayName
    } else {
        choco install $pkg.Name -y --no-progress 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Done $pkg.DisplayName
        } else {
            Write-Fail "$($pkg.DisplayName) — install failed"
        }
    }
}

# ── Visual Studio Build Tools ────────────────────────────────────────────────
Write-Step "Visual Studio Build Tools 2022 (C++ workload)"
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vsInstalled = $false
if (Test-Path $vsWhere) {
    $vsPath = & $vsWhere -latest -property installationPath 2>$null
    if ($vsPath) { $vsInstalled = $true }
}
if ($vsInstalled) {
    Write-Skip "Visual Studio Build Tools"
} else {
    Write-Host ""
    Write-Info "Installing VS Build Tools 2022 with C++ workload (this takes 5-10 min)..."
    choco install visualstudio2022buildtools -y --no-progress --params "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Done "Visual Studio Build Tools 2022"
    } else {
        Write-Fail "VS Build Tools — install manually from https://visualstudio.microsoft.com/downloads/"
    }
}

# ── Qt5 for RViz2 ────────────────────────────────────────────────────────────
Write-Step "Qt5 (for RViz2 visualization)"
$qt5Exists = Test-Path "C:\Qt" -or (Get-ChildItem "C:\Qt\5*" -ErrorAction SilentlyContinue)
if ($qt5Exists) {
    Write-Skip "Qt5"
} else {
    Write-Host ""
    Write-Info "Note: Qt5 may need manual install via https://www.qt.io/download-open-source"
    Write-Info "      Or install via: choco install qt5-default -y"
    choco install qt5-default -y --no-progress 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Done "Qt5"
    } else {
        Write-Fail "Qt5 — you can skip this if you don't need RViz2 GUI"
    }
}

# Refresh PATH after all choco installs
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 3: ROS 2 Humble Core Installation
# ═════════════════════════════════════════════════════════════════════════════
Write-Phase 3 $totalPhases "ROS 2 Humble Desktop (Binary Release)"

Write-Step "Checking existing ROS 2 installation"
if (Test-Path "$ROS2_DIR\local_setup.ps1") {
    Write-Skip "ROS 2 Humble at $ROS2_DIR"
} else {
    Write-Host ""
    $zipPath = "$DOWNLOAD_DIR\ros2-humble-windows.zip"

    if (Test-Path $zipPath) {
        Write-Info "Using cached download: $zipPath"
    } else {
        Write-Info "Downloading ROS 2 Humble binary release (~1.5 GB)..."
        Write-Info "URL: $ROS2_ZIP_URL"
        Write-Info "This will take a while depending on your internet speed..."

        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $ROS2_ZIP_URL -OutFile $zipPath -UseBasicParsing
            $ProgressPreference = 'Continue'
            Write-Done "Download complete ($([math]::Round((Get-Item $zipPath).Length / 1MB)) MB)"
        } catch {
            Write-Fail "Download failed: $_"
            Write-Info "Manual download: $ROS2_ZIP_URL"
            Write-Info "Extract to: $ROS2_DIR"
            Write-Info "Then re-run this script."
            exit 1
        }
    }

    Write-Step "Extracting ROS 2 to $ROS2_DIR"
    Write-Host ""
    Write-Info "Extracting (this takes 2-5 minutes)..."
    New-Item -ItemType Directory -Force -Path $ROS2_DIR | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath "C:\dev" -Force
    # The zip usually extracts to a subfolder — move contents if needed
    $extracted = Get-ChildItem "C:\dev\ros2-windows" -ErrorAction SilentlyContinue
    if ($extracted) {
        Move-Item -Path "C:\dev\ros2-windows\*" -Destination $ROS2_DIR -Force -ErrorAction SilentlyContinue
        Remove-Item "C:\dev\ros2-windows" -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Done "ROS 2 Humble extracted to $ROS2_DIR"
}

# Source ROS 2 environment
Write-Step "Sourcing ROS 2 environment"
if (Test-Path "$ROS2_DIR\local_setup.ps1") {
    . "$ROS2_DIR\local_setup.ps1"
    Write-Done "ROS 2 environment sourced"
} else {
    Write-Fail "local_setup.ps1 not found at $ROS2_DIR"
    Write-Info "Check if extraction path is correct."
}

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 4: Python ROS 2 Tools (pip)
# ═════════════════════════════════════════════════════════════════════════════
Write-Phase 4 $totalPhases "Python ROS 2 Tools"

$pipPackages = @(
    @{Name="colcon-common-extensions"; DisplayName="colcon (ROS 2 build tool)"},
    @{Name="rosdep";                   DisplayName="rosdep (dependency resolver)"},
    @{Name="vcstool";                  DisplayName="vcstool (multi-repo VCS)"},
    @{Name="lark";                     DisplayName="lark (launch file parser)"},
    @{Name="transforms3d";             DisplayName="transforms3d (TF2 math)"},
    @{Name="netifaces";                DisplayName="netifaces (network interfaces)"},
    @{Name="catkin_pkg";               DisplayName="catkin_pkg (package metadata)"},
    @{Name="empy";                     DisplayName="empy (template engine)"}
)

foreach ($pkg in $pipPackages) {
    Write-Step $pkg.DisplayName
    $check = pip show $pkg.Name 2>$null
    if ($check) {
        Write-Skip $pkg.DisplayName
    } else {
        pip install $pkg.Name --quiet 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Done $pkg.DisplayName
        } else {
            Write-Fail "$($pkg.DisplayName) — pip install failed"
        }
    }
}

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 5: ROS 2 Navigation2 Workspace
# ═════════════════════════════════════════════════════════════════════════════
Write-Phase 5 $totalPhases "Navigation2 Workspace Setup"

Write-Step "Creating ROS 2 workspace at $ROS2_WS"
New-Item -ItemType Directory -Force -Path "$ROS2_WS\src" | Out-Null
Write-Done "Workspace directory created"

# Create a .repos file for Nav2 source build
$reposContent = @"
repositories:
  navigation2:
    type: git
    url: https://github.com/ros-navigation/navigation2.git
    version: humble
  slam_toolbox:
    type: git
    url: https://github.com/SteveMacenski/slam_toolbox.git
    version: humble
  robot_localization:
    type: git
    url: https://github.com/cra-ros-pkg/robot_localization.git
    version: humble
"@

$reposFile = "$ROS2_WS\nav2.repos"
Write-Step "Creating nav2.repos manifest"
$reposContent | Out-File -FilePath $reposFile -Encoding utf8
Write-Done "nav2.repos created"

Write-Step "Cloning Nav2 + SLAM + Localization source repos"
Write-Host ""
Write-Info "Cloning Navigation2, slam_toolbox, robot_localization..."
Write-Info "This downloads ~500 MB of source code..."
Push-Location "$ROS2_WS"
try {
    Get-Content $reposFile | vcs import src 2>$null
    Write-Done "All repos cloned into $ROS2_WS\src"
} catch {
    Write-Fail "vcs import failed: $_"
    Write-Info "Try manually: cd $ROS2_WS; vcs import src --input nav2.repos"
}
Pop-Location

# ── rosdep init + update ─────────────────────────────────────────────────────
Write-Step "Initializing rosdep"
$rosdepInitialized = Test-Path "$env:USERPROFILE\.ros\rosdep\sources.cache"
if ($rosdepInitialized) {
    Write-Skip "rosdep already initialized"
} else {
    try {
        rosdep init 2>$null
        Write-Done "rosdep initialized"
    } catch {
        Write-Info "rosdep init may need to be run manually"
    }
}

Write-Step "Updating rosdep database"
try {
    rosdep update 2>$null
    Write-Done "rosdep database updated"
} catch {
    Write-Fail "rosdep update failed — run manually: rosdep update"
}

# ── Install Nav2 dependencies via rosdep ─────────────────────────────────────
Write-Step "Installing Nav2 dependencies via rosdep"
Write-Host ""
Write-Info "Resolving and installing all Nav2 build dependencies..."
Push-Location "$ROS2_WS"
try {
    rosdep install --from-paths src --ignore-src -r -y 2>$null
    Write-Done "Nav2 dependencies installed"
} catch {
    Write-Info "Some dependencies may fail on Windows — this is normal"
    Write-Info "We will handle missing deps during colcon build"
}
Pop-Location

# ── Build Nav2 workspace ─────────────────────────────────────────────────────
Write-Step "Building Nav2 workspace with colcon"
Write-Host ""
Write-Info "Building Navigation2 from source (this takes 15-45 minutes)..."
Write-Info "Using all available CPU cores for compilation..."
Push-Location "$ROS2_WS"
try {
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | Tee-Object -FilePath "$ROS2_WS\build_log.txt"
    if ($LASTEXITCODE -eq 0) {
        Write-Done "Nav2 workspace built successfully"
    } else {
        Write-Fail "Build had errors — check $ROS2_WS\build_log.txt"
        Write-Info "Common fix: install missing deps and re-run colcon build"
    }
} catch {
    Write-Fail "colcon build failed: $_"
    Write-Info "Build log saved to: $ROS2_WS\build_log.txt"
}
Pop-Location

# ═════════════════════════════════════════════════════════════════════════════
# PHASE 6: Verification
# ═════════════════════════════════════════════════════════════════════════════
Write-Phase 6 $totalPhases "Verification"

# Source both ROS 2 core and workspace
if (Test-Path "$ROS2_DIR\local_setup.ps1") {
    . "$ROS2_DIR\local_setup.ps1"
}
if (Test-Path "$ROS2_WS\install\local_setup.ps1") {
    . "$ROS2_WS\install\local_setup.ps1"
}

$tests = @(
    @{Cmd="ros2 --version";                      Desc="ROS 2 CLI"},
    @{Cmd="python -c `"import rclpy; print('rclpy OK')`""; Desc="rclpy Python bindings"},
    @{Cmd="ros2 pkg list 2>`$null | Select-String nav2"; Desc="Nav2 packages"}
)

foreach ($test in $tests) {
    Write-Step $test.Desc
    try {
        $output = Invoke-Expression $test.Cmd 2>$null
        if ($output) {
            Write-Done "$($test.Desc): $output"
        } else {
            Write-Fail "$($test.Desc): no output"
        }
    } catch {
        Write-Fail "$($test.Desc): $_"
    }
}

# ═════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ROS 2 Humble + Nav2 Setup Complete!                    ║" -ForegroundColor Green
Write-Host "║                                                          ║" -ForegroundColor Green
Write-Host "║   Installed to:                                          ║" -ForegroundColor Green
Write-Host "║     ROS 2 Core:  $ROS2_DIR                    ║" -ForegroundColor Green
Write-Host "║     Nav2 WS:     $ROS2_WS                        ║" -ForegroundColor Green
Write-Host "║                                                          ║" -ForegroundColor Green
Write-Host "║   To use ROS 2 in any new PowerShell window:             ║" -ForegroundColor Green
Write-Host "║     . C:\dev\ros2_humble\local_setup.ps1                 ║" -ForegroundColor Green
Write-Host "║     . C:\dev\ros2_ws\install\local_setup.ps1             ║" -ForegroundColor Green
Write-Host "║                                                          ║" -ForegroundColor Green
Write-Host "║   Quick test:                                            ║" -ForegroundColor Green
Write-Host "║     ros2 run demo_nodes_cpp talker                       ║" -ForegroundColor Green
Write-Host "║     ros2 run demo_nodes_py listener  (in 2nd terminal)   ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# ── Create environment loader script ─────────────────────────────────────────
$loaderScript = @"
# source_ros2.ps1 — Run this at the start of every PowerShell session
# Usage: . .\source_ros2.ps1

Write-Host "Loading ROS 2 Humble environment..." -ForegroundColor Cyan
. C:\dev\ros2_humble\local_setup.ps1
if (Test-Path "C:\dev\ros2_ws\install\local_setup.ps1") {
    . C:\dev\ros2_ws\install\local_setup.ps1
    Write-Host "Nav2 workspace loaded." -ForegroundColor Green
}
Write-Host "ROS 2 ready. Try: ros2 topic list" -ForegroundColor Green
"@

$loaderPath = "C:\dev\source_ros2.ps1"
$loaderScript | Out-File -FilePath $loaderPath -Encoding utf8
Write-Info "Created environment loader: $loaderPath"
Write-Info "Run `. C:\dev\source_ros2.ps1` in every new terminal."
Write-Host ""

# setup_ros2_windows.ps1 -- Swachh Boudhik Yantra
# ROS 2 Humble + Navigation2 Full Setup for Windows 11 GPU System
#
# Run as Administrator in PowerShell:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup_ros2_windows.ps1
#
# Prerequisites: Internet connection (via RPi NAT forwarding or USB tether)

$ErrorActionPreference = "Continue"   # Don't stop on non-fatal errors
$ROS2_ZIP_URL  = "https://github.com/ros2/ros2/releases/download/release-humble-20250415/ros2-humble-20250415-windows-release-amd64.zip"
$ROS2_DIR      = "C:\dev\ros2_humble"
$ROS2_WS       = "C:\dev\ros2_ws"
$DOWNLOAD_DIR  = "$env:TEMP\ros2_setup"

# -- Colour + Progress Helpers ------------------------------------------------
function Write-Phase { param($num, $total, $msg)
    Write-Host ""
    Write-Host "=======================================================" -ForegroundColor DarkCyan
    Write-Host "  Phase $num/$total -- $msg" -ForegroundColor Cyan
    Write-Host "=======================================================" -ForegroundColor DarkCyan
}
function Write-Step { param($msg) Write-Host "  [ ] $msg ..." -ForegroundColor White }
function Write-Done { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Skip { param($msg) Write-Host "  [--] $msg (already installed)" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "  --> $msg" -ForegroundColor DarkGray }

# -- Admin Check --------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Host "`n  ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "  Right-click PowerShell -> Run as Administrator`n" -ForegroundColor Yellow
    exit 1
}

# -- Banner -------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "  Swachh Boudhik Yantra -- ROS 2 Humble + Nav2 Setup" -ForegroundColor Magenta
Write-Host "  Target: Windows 11 / NVIDIA RTX A6000" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

$totalPhases = 6
New-Item -ItemType Directory -Force -Path $DOWNLOAD_DIR | Out-Null

# =============================================================================
# PHASE 1: Chocolatey
# =============================================================================
Write-Phase 1 $totalPhases "Chocolatey Package Manager"

Write-Step "Checking Chocolatey"
$chocoCmd = Get-Command choco -ErrorAction SilentlyContinue
if ($chocoCmd) {
    Write-Skip "Chocolatey $( choco --version )"
} else {
    Write-Info "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Done "Chocolatey installed"
}

# =============================================================================
# PHASE 2: System Prerequisites
# =============================================================================
Write-Phase 2 $totalPhases "System Prerequisites (via Chocolatey)"

$chocoPackages = @(
    @{Name="cmake";       DisplayName="CMake (Build System)"},
    @{Name="git";         DisplayName="Git"},
    @{Name="openssl";     DisplayName="OpenSSL (DDS Security)"},
    @{Name="vcredist140"; DisplayName="Visual C++ Redistributable 2015-2022"},
    @{Name="graphviz";    DisplayName="Graphviz (rqt graph tools)"},
    @{Name="wget";        DisplayName="wget (download utility)"}
)

foreach ($pkg in $chocoPackages) {
    Write-Step $pkg.DisplayName
    $installed = choco list --local-only --exact $pkg.Name 2>$null | Select-String $pkg.Name
    if ($installed) {
        Write-Skip $pkg.DisplayName
    } else {
        choco install $pkg.Name -y --no-progress 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Done $pkg.DisplayName }
        else { Write-Fail "$($pkg.DisplayName) -- install failed (non-fatal, continuing)" }
    }
}

# -- Visual Studio Build Tools ------------------------------------------------
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
    Write-Info "Installing VS Build Tools 2022 with C++ workload (5-10 min)..."
    choco install visualstudio2022buildtools -y --no-progress --params "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Done "Visual Studio Build Tools 2022" }
    else { Write-Fail "VS Build Tools -- install manually from https://visualstudio.microsoft.com/downloads/" }
}

# -- Qt5 for RViz2 (FIXED: was Test-Path "C:\Qt" -or ...) --------------------
Write-Step "Qt5 (for RViz2 visualization)"
$qt5Exists = (Test-Path "C:\Qt") -or ($null -ne (Get-ChildItem "C:\Qt" -Filter "5*" -ErrorAction SilentlyContinue))
if ($qt5Exists) {
    Write-Skip "Qt5"
} else {
    Write-Info "Attempting Qt5 via choco (may fail -- that is OK, RViz2 optional)"
    choco install qt5-default -y --no-progress 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Done "Qt5" }
    else { Write-Fail "Qt5 not installed -- RViz2 GUI will not work, rest of ROS 2 is fine" }
}

# Refresh PATH after all choco installs
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# =============================================================================
# PHASE 3: ROS 2 Humble Core
# =============================================================================
Write-Phase 3 $totalPhases "ROS 2 Humble Desktop (Binary Release)"

Write-Step "Checking existing ROS 2 installation"
if (Test-Path "$ROS2_DIR\local_setup.ps1") {
    Write-Skip "ROS 2 Humble already at $ROS2_DIR"
} else {
    Write-Host ""
    $zipPath = "$DOWNLOAD_DIR\ros2-humble-windows.zip"

    if (Test-Path $zipPath) {
        Write-Info "Using cached download: $zipPath"
    } else {
        Write-Info "Downloading ROS 2 Humble (~1.5 GB) -- this takes 10-30 min depending on speed..."
        Write-Info "URL: $ROS2_ZIP_URL"
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $ROS2_ZIP_URL -OutFile $zipPath -UseBasicParsing
            $ProgressPreference = 'Continue'
            $sizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB)
            Write-Done "Download complete ($sizeMB MB)"
        } catch {
            Write-Fail "Download failed: $_"
            Write-Info "Manual download URL: $ROS2_ZIP_URL"
            Write-Info "Save to: $zipPath"
            Write-Info "Then re-run this script to continue from extraction."
        }
    }

    if (Test-Path $zipPath) {
        Write-Step "Extracting ROS 2 to $ROS2_DIR"
        Write-Info "Extracting (2-5 minutes)..."
        New-Item -ItemType Directory -Force -Path $ROS2_DIR | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath "C:\dev" -Force

        # The zip extracts to ros2-windows subfolder -- move if needed
        $extractedDir = "C:\dev\ros2-windows"
        if (Test-Path $extractedDir) {
            Move-Item -Path "$extractedDir\*" -Destination $ROS2_DIR -Force -ErrorAction SilentlyContinue
            Remove-Item $extractedDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Done "ROS 2 Humble extracted to $ROS2_DIR"
    }
}

# Source ROS 2 environment
Write-Step "Sourcing ROS 2 environment"
if (Test-Path "$ROS2_DIR\local_setup.ps1") {
    . "$ROS2_DIR\local_setup.ps1"
    Write-Done "ROS 2 environment sourced"
} else {
    Write-Fail "local_setup.ps1 not found -- Phase 3 download/extract may have failed"
}

# =============================================================================
# PHASE 4: Python ROS 2 Tools (pip)
# =============================================================================
Write-Phase 4 $totalPhases "Python ROS 2 Tools (pip)"

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
        if ($LASTEXITCODE -eq 0) { Write-Done $pkg.DisplayName }
        else { Write-Fail "$($pkg.DisplayName) -- pip install failed" }
    }
}

# =============================================================================
# PHASE 5: Navigation2 Workspace
# =============================================================================
Write-Phase 5 $totalPhases "Navigation2 Workspace Setup"

Write-Step "Creating ROS 2 workspace at $ROS2_WS"
New-Item -ItemType Directory -Force -Path "$ROS2_WS\src" | Out-Null
Write-Done "Workspace directory created"

# Write nav2.repos file
$reposFile = "$ROS2_WS\nav2.repos"
Write-Step "Creating nav2.repos manifest"
$reposLines = @(
    "repositories:",
    "  navigation2:",
    "    type: git",
    "    url: https://github.com/ros-navigation/navigation2.git",
    "    version: humble",
    "  slam_toolbox:",
    "    type: git",
    "    url: https://github.com/SteveMacenski/slam_toolbox.git",
    "    version: humble",
    "  robot_localization:",
    "    type: git",
    "    url: https://github.com/cra-ros-pkg/robot_localization.git",
    "    version: humble"
)
$reposLines | Out-File -FilePath $reposFile -Encoding utf8
Write-Done "nav2.repos created at $reposFile"

# Clone repos via vcs
Write-Step "Cloning Nav2 + SLAM + Localization repos (~500 MB)"
Write-Info "This may take 5-15 minutes depending on internet speed..."
$vcscmd = Get-Command vcs -ErrorAction SilentlyContinue
if ($vcscmd) {
    Push-Location "$ROS2_WS"
    vcs import src --input $reposFile 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Done "All repos cloned" }
    else { Write-Fail "vcs import had errors -- check output above" }
    Pop-Location
} else {
    Write-Fail "vcs not found -- run: pip install vcstool   then re-run this script"
}

# rosdep init + update
Write-Step "Initializing rosdep"
$rosdepCache = "$env:USERPROFILE\.ros\rosdep\sources.list.d"
if (Test-Path $rosdepCache) {
    Write-Skip "rosdep already initialized"
} else {
    rosdep init 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Done "rosdep initialized" }
    else { Write-Fail "rosdep init failed -- try: rosdep init  manually" }
}

Write-Step "Updating rosdep database"
rosdep update 2>&1
if ($LASTEXITCODE -eq 0) { Write-Done "rosdep database updated" }
else { Write-Fail "rosdep update failed -- run: rosdep update  manually" }

# Install Nav2 dependencies via rosdep
Write-Step "Installing Nav2 dependencies via rosdep"
Push-Location "$ROS2_WS"
rosdep install --from-paths src --ignore-src -r -y 2>&1
Write-Info "rosdep finished (some Windows failures are expected and non-fatal)"
Pop-Location

# Build Nav2 workspace with colcon
Write-Step "Building Nav2 workspace with colcon (15-45 min)"
Write-Info "This is the longest step -- output will stream below..."
$colconCmd = Get-Command colcon -ErrorAction SilentlyContinue
if ($colconCmd) {
    Push-Location "$ROS2_WS"
    $buildLog = "$ROS2_WS\build_log.txt"
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | Tee-Object -FilePath $buildLog
    if ($LASTEXITCODE -eq 0) { Write-Done "Nav2 workspace built successfully" }
    else {
        Write-Fail "Build had errors -- see $buildLog"
        Write-Info "Tip: re-run colcon build to continue from where it stopped"
    }
    Pop-Location
} else {
    Write-Fail "colcon not found -- install with: pip install colcon-common-extensions"
}

# =============================================================================
# PHASE 6: Verification
# =============================================================================
Write-Phase 6 $totalPhases "Verification"

# Source environments
if (Test-Path "$ROS2_DIR\local_setup.ps1")          { . "$ROS2_DIR\local_setup.ps1" }
if (Test-Path "$ROS2_WS\install\local_setup.ps1")   { . "$ROS2_WS\install\local_setup.ps1" }

$checks = @(
    @{ Desc="ROS 2 CLI version";     Cmd={ ros2 --version 2>$null } },
    @{ Desc="rclpy Python bindings"; Cmd={ python -c "import rclpy; print('rclpy OK')" 2>$null } },
    @{ Desc="Nav2 packages present"; Cmd={ ros2 pkg list 2>$null | Select-String "nav2" } }
)

foreach ($chk in $checks) {
    Write-Step $chk.Desc
    try {
        $out = & $chk.Cmd
        if ($out) { Write-Done "$($chk.Desc): $out" }
        else      { Write-Fail "$($chk.Desc): no output (may need ROS 2 sourced)" }
    } catch {
        Write-Fail "$($chk.Desc): $_"
    }
}

# =============================================================================
# FINAL SUMMARY
# =============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  ROS 2 Humble + Nav2 Setup Complete!" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "  Installed to:" -ForegroundColor Green
Write-Host "    ROS 2 Core : $ROS2_DIR" -ForegroundColor Green
Write-Host "    Nav2 WS    : $ROS2_WS" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "  To use ROS 2 in any new PowerShell window:" -ForegroundColor Green
Write-Host "    . C:\dev\ros2_humble\local_setup.ps1" -ForegroundColor Green
Write-Host "    . C:\dev\ros2_ws\install\local_setup.ps1" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "  Quick test:" -ForegroundColor Green
Write-Host "    ros2 run demo_nodes_cpp talker" -ForegroundColor Green
Write-Host "    ros2 run demo_nodes_py listener  (in 2nd terminal)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

# Create convenience loader script
$loaderPath = "C:\dev\source_ros2.ps1"
New-Item -ItemType Directory -Force -Path "C:\dev" | Out-Null
$loaderLines = @(
    "# source_ros2.ps1 -- Run this at the start of every ROS 2 session",
    "# Usage: . C:\dev\source_ros2.ps1",
    "",
    "Write-Host 'Loading ROS 2 Humble environment...' -ForegroundColor Cyan",
    ". C:\dev\ros2_humble\local_setup.ps1",
    "if (Test-Path 'C:\dev\ros2_ws\install\local_setup.ps1') {",
    "    . C:\dev\ros2_ws\install\local_setup.ps1",
    "    Write-Host 'Nav2 workspace loaded.' -ForegroundColor Green",
    "}",
    "Write-Host 'ROS 2 ready. Try: ros2 topic list' -ForegroundColor Green"
)
$loaderLines | Out-File -FilePath $loaderPath -Encoding utf8
Write-Info "Created environment loader: $loaderPath"
Write-Info "Run '. C:\dev\source_ros2.ps1' in every new terminal."
Write-Host ""

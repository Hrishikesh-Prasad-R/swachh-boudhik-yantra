# setup_ros2_windows.ps1 -- Swachh Boudhik Yantra
# ROS 2 Humble + Navigation2 Full Setup for Windows 11 GPU System
# Run as Administrator. Progress is logged to C:\dev\ros2_progress.json

$ErrorActionPreference = "Continue"
$ROS2_ZIP_URL = "https://github.com/ros2/ros2/releases/download/release-humble-20250415/ros2-humble-20250415-windows-release-amd64.zip"
$ROS2_DIR     = "C:\dev\ros2_humble"
$ROS2_WS      = "C:\dev\ros2_ws"
$DOWNLOAD_DIR = "$env:TEMP\ros2_setup"
$PROGRESS_FILE = "C:\dev\ros2_progress.json"

New-Item -ItemType Directory -Force -Path "C:\dev" | Out-Null
New-Item -ItemType Directory -Force -Path $DOWNLOAD_DIR | Out-Null

# ── Progress helpers ──────────────────────────────────────────────────────────
function Set-Progress {
    param([int]$PhaseNum, [string]$PhaseName, [int]$TaskNum, [int]$TaskTotal,
          [string]$TaskName, [string]$Status, [string]$Detail = "")
    $pct = if ($TaskTotal -gt 0) { [math]::Round(($TaskNum / $TaskTotal) * 100) } else { 0 }
    $obj = [ordered]@{
        phase_num   = $PhaseNum
        phase_name  = $PhaseName
        task_num    = $TaskNum
        task_total  = $TaskTotal
        task_name   = $TaskName
        status      = $Status   # running / done / fail / skip
        pct         = $pct
        detail      = $Detail
        timestamp   = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    }
    $obj | ConvertTo-Json -Compress | Out-File -FilePath $PROGRESS_FILE -Encoding utf8 -Force
}

function Write-Phase { param($num, $total, $msg)
    Write-Host ""
    Write-Host "=======================================================" -ForegroundColor DarkCyan
    Write-Host "  Phase $num/$total -- $msg" -ForegroundColor Cyan
    Write-Host "=======================================================" -ForegroundColor DarkCyan
}
function Write-Step { param($msg) Write-Host "  [ ] $msg ..." -ForegroundColor White }
function Write-Done { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Skip { param($msg) Write-Host "  [--] $msg (already done)" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "  --> $msg" -ForegroundColor DarkGray }

# ── Admin check ───────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Host "`n  ERROR: Run as Administrator!" -ForegroundColor Red; exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "  Swachh Boudhik Yantra -- ROS 2 Humble + Nav2 Setup" -ForegroundColor Magenta
Write-Host "  Progress file: $PROGRESS_FILE" -ForegroundColor DarkGray
Write-Host "  Monitor with: .\monitor_ros2.ps1 (in any other terminal)" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

# =============================================================================
# PHASE 1 -- Chocolatey  (1 task)
# =============================================================================
Write-Phase 1 6 "Chocolatey Package Manager"
Set-Progress 1 "Chocolatey" 0 1 "Install Chocolatey" "running"

Write-Step "Chocolatey"
$chocoCmd = Get-Command choco -ErrorAction SilentlyContinue
if ($chocoCmd) {
    Write-Skip "Chocolatey $(choco --version)"
    Set-Progress 1 "Chocolatey" 1 1 "Chocolatey" "skip" "v$(choco --version)"
} else {
    Write-Info "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Done "Chocolatey installed"
        Set-Progress 1 "Chocolatey" 1 1 "Chocolatey" "done" "v$(choco --version)"
    } else {
        Write-Fail "Chocolatey install failed"
        Set-Progress 1 "Chocolatey" 1 1 "Chocolatey" "fail"
    }
}

# =============================================================================
# PHASE 2 -- System Prerequisites  (7 tasks)
# =============================================================================
Write-Phase 2 6 "System Prerequisites"

$chocoPackages = @(
    @{Name="cmake";       Display="CMake"},
    @{Name="git";         Display="Git"},
    @{Name="openssl";     Display="OpenSSL"},
    @{Name="vcredist140"; Display="VC++ Redistributable"},
    @{Name="graphviz";    Display="Graphviz"},
    @{Name="wget";        Display="wget"}
)

$p2total = 7   # 6 choco + VS Build Tools
$p2i = 0

foreach ($pkg in $chocoPackages) {
    $p2i++
    Set-Progress 2 "Prerequisites" $p2i $p2total $pkg.Display "running"
    Write-Step $pkg.Display
    $installed = choco list --local-only --exact $pkg.Name 2>$null | Select-String $pkg.Name
    if ($installed) {
        Write-Skip $pkg.Display
        Set-Progress 2 "Prerequisites" $p2i $p2total $pkg.Display "skip"
    } else {
        choco install $pkg.Name -y --no-progress 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Done $pkg.Display
            Set-Progress 2 "Prerequisites" $p2i $p2total $pkg.Display "done"
        } else {
            Write-Fail "$($pkg.Display) failed (non-fatal)"
            Set-Progress 2 "Prerequisites" $p2i $p2total $pkg.Display "fail"
        }
    }
}

# VS Build Tools
$p2i++
Set-Progress 2 "Prerequisites" $p2i $p2total "VS Build Tools 2022" "running" "checking..."
Write-Step "VS Build Tools 2022"
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vsInstalled = (Test-Path $vsWhere) -and (& $vsWhere -latest -property installationPath 2>$null)
if ($vsInstalled) {
    Write-Skip "VS Build Tools"
    Set-Progress 2 "Prerequisites" $p2i $p2total "VS Build Tools 2022" "skip"
} else {
    Write-Info "Installing VS Build Tools 2022 (5-10 min)..."
    Set-Progress 2 "Prerequisites" $p2i $p2total "VS Build Tools 2022" "running" "installing C++ workload (5-10 min)..."
    choco install visualstudio2022buildtools -y --no-progress --params "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Done "VS Build Tools 2022"
        Set-Progress 2 "Prerequisites" $p2i $p2total "VS Build Tools 2022" "done"
    } else {
        Write-Fail "VS Build Tools failed"
        Set-Progress 2 "Prerequisites" $p2i $p2total "VS Build Tools 2022" "fail"
    }
}

# Qt5 (optional, non-fatal)
Write-Step "Qt5 (optional, for RViz2)"
$qt5ok = Test-Path "C:\Qt"
if ($qt5ok) {
    Write-Skip "Qt5"
} else {
    choco install qt5-default -y --no-progress 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Done "Qt5" } else { Write-Fail "Qt5 not available via choco (optional -- skipping)" }
}

$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
Set-Progress 2 "Prerequisites" 7 7 "All prerequisites" "done"

# =============================================================================
# PHASE 3 -- ROS 2 Humble  (3 tasks: download, extract, source)
# =============================================================================
Write-Phase 3 6 "ROS 2 Humble Desktop (Binary)"

if (Test-Path "$ROS2_DIR\local_setup.ps1") {
    Write-Skip "ROS 2 Humble (already at $ROS2_DIR)"
    Set-Progress 3 "ROS 2 Humble" 3 3 "Already installed" "skip"
} else {
    $zipPath = "$DOWNLOAD_DIR\ros2-humble-windows.zip"

    # Task 3.1 -- Download
    Set-Progress 3 "ROS 2 Humble" 1 3 "Downloading zip (~1.5 GB)" "running" "starting download..."
    if (Test-Path $zipPath) {
        $cachedMB = [math]::Round((Get-Item $zipPath).Length/1MB)
        Write-Info "Using cached zip ($cachedMB MB)"
        Set-Progress 3 "ROS 2 Humble" 1 3 "Downloading zip" "skip" "cached ($cachedMB MB)"
    } else {
        Write-Info "Downloading ROS 2 Humble (~1.5 GB) via BITS -- this shows real-time progress..."
        Write-Info "URL: $ROS2_ZIP_URL"

        # Use Windows BITS (Background Intelligent Transfer Service) -- handles large files, resumes on failure
        try {
            $bitsJob = Start-BitsTransfer -Source $ROS2_ZIP_URL -Destination $zipPath -Asynchronous -DisplayName "ROS2 Humble Download"
            $startTime = Get-Date
            while ($bitsJob.JobState -notin @('Transferred','Error','TransientError')) {
                Start-Sleep -Seconds 4
                $mbDone  = [math]::Round($bitsJob.BytesTransferred / 1MB)
                $mbTotal = if ($bitsJob.BytesTotal -gt 0) { [math]::Round($bitsJob.BytesTotal / 1MB) } else { 1500 }
                $pct     = if ($mbTotal -gt 0) { [math]::Round($mbDone / $mbTotal * 100) } else { 0 }
                $elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds)
                $detail  = "${mbDone}/${mbTotal} MB  ${pct}%  (${elapsed}s)"
                Set-Progress 3 "ROS 2 Humble" 1 3 "Downloading zip (~1500 MB)" "running" $detail
                Write-Host "  --> $detail" -ForegroundColor DarkGray
            }
            if ($bitsJob.JobState -eq 'Transferred') {
                Complete-BitsTransfer -BitsJob $bitsJob
                $finalMB = [math]::Round((Get-Item $zipPath).Length / 1MB)
                Write-Done "Download complete ($finalMB MB)"
                Set-Progress 3 "ROS 2 Humble" 1 3 "Download complete" "done" "$finalMB MB"
            } else {
                Remove-BitsTransfer -BitsJob $bitsJob
                throw "BITS job state: $($bitsJob.JobState)"
            }
        } catch {
            Write-Fail "BITS download failed: $_ -- trying direct download as fallback..."
            Set-Progress 3 "ROS 2 Humble" 1 3 "Downloading (fallback)" "running" "using Invoke-WebRequest..."
            try {
                $ProgressPreference = 'SilentlyContinue'
                Invoke-WebRequest -Uri $ROS2_ZIP_URL -OutFile $zipPath -UseBasicParsing
                $ProgressPreference = 'Continue'
                $finalMB = [math]::Round((Get-Item $zipPath).Length / 1MB)
                Write-Done "Download complete ($finalMB MB)"
                Set-Progress 3 "ROS 2 Humble" 1 3 "Download complete" "done" "$finalMB MB"
            } catch {
                Write-Fail "Download failed: $_ -- download manually to: $zipPath"
                Set-Progress 3 "ROS 2 Humble" 1 3 "Download" "fail" "both BITS and IWR failed"
            }
        }
    }

    # Task 3.2 -- Extract
    if (Test-Path $zipPath) {
        Set-Progress 3 "ROS 2 Humble" 2 3 "Extracting zip (2-5 min)" "running"
        Write-Step "Extracting to $ROS2_DIR"
        Write-Info "This takes 2-5 minutes..."
        New-Item -ItemType Directory -Force -Path $ROS2_DIR | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath "C:\dev" -Force
        if (Test-Path "C:\dev\ros2-windows") {
            Move-Item -Path "C:\dev\ros2-windows\*" -Destination $ROS2_DIR -Force -ErrorAction SilentlyContinue
            Remove-Item "C:\dev\ros2-windows" -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Done "Extracted to $ROS2_DIR"
        Set-Progress 3 "ROS 2 Humble" 2 3 "Extraction" "done"
    }

    # Task 3.3 -- Source
    Set-Progress 3 "ROS 2 Humble" 3 3 "Sourcing environment" "running"
    if (Test-Path "$ROS2_DIR\local_setup.ps1") {
        . "$ROS2_DIR\local_setup.ps1"
        Write-Done "ROS 2 environment sourced"
        Set-Progress 3 "ROS 2 Humble" 3 3 "Environment sourced" "done"
    } else {
        Write-Fail "local_setup.ps1 not found -- extraction may have failed"
        Set-Progress 3 "ROS 2 Humble" 3 3 "Source env" "fail"
    }
}

# =============================================================================
# PHASE 4 -- Python pip tools  (8 tasks)
# =============================================================================
Write-Phase 4 6 "Python ROS 2 Tools (pip)"

$pipPkgs = @(
    @{Name="colcon-common-extensions"; Display="colcon"},
    @{Name="rosdep";                   Display="rosdep"},
    @{Name="vcstool";                  Display="vcstool"},
    @{Name="lark";                     Display="lark"},
    @{Name="transforms3d";             Display="transforms3d"},
    @{Name="netifaces";                Display="netifaces"},
    @{Name="catkin_pkg";               Display="catkin_pkg"},
    @{Name="empy";                     Display="empy"}
)

$p4i = 0
foreach ($pkg in $pipPkgs) {
    $p4i++
    Set-Progress 4 "pip packages" $p4i $pipPkgs.Count $pkg.Display "running"
    Write-Step $pkg.Display
    if (pip show $pkg.Name 2>$null) {
        Write-Skip $pkg.Display
        Set-Progress 4 "pip packages" $p4i $pipPkgs.Count $pkg.Display "skip"
    } else {
        pip install $pkg.Name --quiet 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Done $pkg.Display
            Set-Progress 4 "pip packages" $p4i $pipPkgs.Count $pkg.Display "done"
        } else {
            Write-Fail "$($pkg.Display) failed"
            Set-Progress 4 "pip packages" $p4i $pipPkgs.Count $pkg.Display "fail"
        }
    }
}

# =============================================================================
# PHASE 5 -- Navigation2 Workspace  (6 tasks)
# =============================================================================
Write-Phase 5 6 "Navigation2 Workspace"

# 5.1 Create workspace
Set-Progress 5 "Nav2 Workspace" 1 6 "Create workspace dirs" "running"
Write-Step "Creating workspace at $ROS2_WS"
New-Item -ItemType Directory -Force -Path "$ROS2_WS\src" | Out-Null
Write-Done "Workspace created"
Set-Progress 5 "Nav2 Workspace" 1 6 "Create workspace dirs" "done"

# 5.2 Write nav2.repos  (MUST be UTF-8 no-BOM + LF endings -- Python vcs rejects BOM)
Set-Progress 5 "Nav2 Workspace" 2 6 "Write nav2.repos" "running"
$reposFile = "$ROS2_WS\nav2.repos"
$yamlContent = "repositories:`n  navigation2:`n    type: git`n    url: https://github.com/ros-navigation/navigation2.git`n    version: humble`n  slam_toolbox:`n    type: git`n    url: https://github.com/SteveMacenski/slam_toolbox.git`n    version: humble`n  robot_localization:`n    type: git`n    url: https://github.com/cra-ros-pkg/robot_localization.git`n    version: humble`n"
[System.IO.File]::WriteAllText($reposFile, $yamlContent, [System.Text.UTF8Encoding]::new($false))
$bomCheck = [System.IO.File]::ReadAllBytes($reposFile)[0..2] | ForEach-Object { '{0:X2}' -f $_ }
Write-Done "nav2.repos written (no BOM: $($bomCheck -join ' '))"
Set-Progress 5 "Nav2 Workspace" 2 6 "Write nav2.repos" "done"

# 5.3 vcs import
Set-Progress 5 "Nav2 Workspace" 3 6 "Clone repos (nav2+slam+localization)" "running" "~500 MB, 5-15 min..."
Write-Step "Cloning repos (~500 MB, 5-15 min)"
$vcscmd = Get-Command vcs -ErrorAction SilentlyContinue
if ($vcscmd) {
    Push-Location "$ROS2_WS"
    vcs import src --input $reposFile 2>&1
    $vcsOk = $LASTEXITCODE -eq 0
    Pop-Location
    if ($vcsOk) {
        Write-Done "All repos cloned"
        Set-Progress 5 "Nav2 Workspace" 3 6 "Clone repos" "done"
    } else {
        Write-Fail "vcs import had errors"
        Set-Progress 5 "Nav2 Workspace" 3 6 "Clone repos" "fail"
    }
} else {
    Write-Fail "vcs not found -- install vcstool first"
    Set-Progress 5 "Nav2 Workspace" 3 6 "Clone repos" "fail" "vcstool missing"
}

# 5.4 rosdep init
Set-Progress 5 "Nav2 Workspace" 4 6 "rosdep init" "running"
Write-Step "rosdep init"
if (Test-Path "$env:USERPROFILE\.ros\rosdep") {
    Write-Skip "rosdep already initialized"
    Set-Progress 5 "Nav2 Workspace" 4 6 "rosdep init" "skip"
} else {
    rosdep init 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Done "rosdep initialized"
        Set-Progress 5 "Nav2 Workspace" 4 6 "rosdep init" "done"
    } else {
        Write-Fail "rosdep init failed (non-fatal)"
        Set-Progress 5 "Nav2 Workspace" 4 6 "rosdep init" "fail"
    }
}

# 5.5 rosdep update
Set-Progress 5 "Nav2 Workspace" 5 6 "rosdep update" "running"
Write-Step "rosdep update"
rosdep update 2>&1
Set-Progress 5 "Nav2 Workspace" 5 6 "rosdep update" "done"

# 5.6 colcon build
Set-Progress 5 "Nav2 Workspace" 6 6 "colcon build (15-45 min)" "running" "compiling Nav2 C++ from source..."
Write-Step "colcon build (15-45 min -- output streaming below)"
Write-Info "Building Navigation2 from source. This is the longest step."
$colconCmd = Get-Command colcon -ErrorAction SilentlyContinue
if ($colconCmd) {
    Push-Location "$ROS2_WS"
    if (Test-Path "$ROS2_DIR\local_setup.ps1") { . "$ROS2_DIR\local_setup.ps1" }
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | Tee-Object -FilePath "$ROS2_WS\build_log.txt"
    if ($LASTEXITCODE -eq 0) {
        Write-Done "Nav2 built successfully"
        Set-Progress 5 "Nav2 Workspace" 6 6 "colcon build" "done"
    } else {
        Write-Fail "Build errors -- see $ROS2_WS\build_log.txt"
        Set-Progress 5 "Nav2 Workspace" 6 6 "colcon build" "fail" "see build_log.txt"
    }
    Pop-Location
} else {
    Write-Fail "colcon not found"
    Set-Progress 5 "Nav2 Workspace" 6 6 "colcon build" "fail" "colcon missing"
}

# =============================================================================
# PHASE 6 -- Verification  (3 tasks)
# =============================================================================
Write-Phase 6 6 "Verification"

if (Test-Path "$ROS2_DIR\local_setup.ps1")        { . "$ROS2_DIR\local_setup.ps1" }
if (Test-Path "$ROS2_WS\install\local_setup.ps1") { . "$ROS2_WS\install\local_setup.ps1" }

$ver_tasks = @(
    @{ Desc="ros2 CLI";          Cmd={ ros2 --version 2>$null } },
    @{ Desc="rclpy bindings";    Cmd={ python -c "import rclpy; print('OK')" 2>$null } },
    @{ Desc="Nav2 packages";     Cmd={ ros2 pkg list 2>$null | Select-String "nav2_bringup" } }
)
$v = 0
foreach ($t in $ver_tasks) {
    $v++
    Set-Progress 6 "Verification" $v 3 $t.Desc "running"
    Write-Step $t.Desc
    try {
        $out = & $t.Cmd
        if ($out) {
            Write-Done "$($t.Desc): $out"
            Set-Progress 6 "Verification" $v 3 $t.Desc "done" "$out"
        } else {
            Write-Fail "$($t.Desc): no output"
            Set-Progress 6 "Verification" $v 3 $t.Desc "fail"
        }
    } catch {
        Write-Fail "$($t.Desc): $_"
        Set-Progress 6 "Verification" $v 3 $t.Desc "fail"
    }
}

Set-Progress 6 "Verification" 3 3 "ALL DONE" "done" "ROS2 Humble + Nav2 ready!"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "  ROS 2 Core : $ROS2_DIR" -ForegroundColor Green
Write-Host "  Nav2 WS    : $ROS2_WS" -ForegroundColor Green
Write-Host "  Source env : . C:\dev\source_ros2.ps1" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

# Write convenience loader
@(
    "# source_ros2.ps1",
    "Write-Host 'Loading ROS 2...' -ForegroundColor Cyan",
    ". C:\dev\ros2_humble\local_setup.ps1",
    "if (Test-Path 'C:\dev\ros2_ws\install\local_setup.ps1') { . C:\dev\ros2_ws\install\local_setup.ps1 }",
    "Write-Host 'Ready. Try: ros2 topic list' -ForegroundColor Green"
) | Out-File -FilePath "C:\dev\source_ros2.ps1" -Encoding utf8
Write-Info "Loader saved: C:\dev\source_ros2.ps1"

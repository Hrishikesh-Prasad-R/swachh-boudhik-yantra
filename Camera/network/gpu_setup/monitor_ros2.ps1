# monitor_ros2.ps1 -- Live progress monitor for ROS 2 setup
# Run this in ANY terminal (no admin needed) while setup_ros2_windows.ps1 runs
# Usage: .\monitor_ros2.ps1

$PROGRESS_FILE = "C:\dev\ros2_progress.json"

$PHASES = @(
    @{ Num=1; Name="Chocolatey";       Total=1 },
    @{ Num=2; Name="Prerequisites";    Total=7 },
    @{ Num=3; Name="ROS 2 Humble";     Total=3 },
    @{ Num=4; Name="pip packages";     Total=8 },
    @{ Num=5; Name="Nav2 Workspace";   Total=6 },
    @{ Num=6; Name="Verification";     Total=3 }
)

function Draw-Bar {
    param([int]$pct, [int]$width = 30)
    $filled = [math]::Round($pct / 100 * $width)
    $empty  = $width - $filled
    return ("[" + ("=" * $filled) + (" " * $empty) + "]")
}

function Get-PhaseStatus {
    param([int]$phaseNum, $progress)
    if ($null -eq $progress) { return @{ pct=0; status="pending"; task=""; detail="" } }
    if ($progress.phase_num -gt $phaseNum) { return @{ pct=100; status="done";    task="Complete"; detail="" } }
    if ($progress.phase_num -eq $phaseNum) {
        $ph = $PHASES | Where-Object { $_.Num -eq $phaseNum }
        $pct = [math]::Round(($progress.task_num / $ph.Total) * 100)
        return @{ pct=$pct; status=$progress.status; task=$progress.task_name; detail=$progress.detail }
    }
    return @{ pct=0; status="pending"; task="Waiting..."; detail="" }
}

function Get-StatusIcon {
    param([string]$status, [int]$pct)
    switch ($status) {
        "done"    { return "[DONE]" }
        "skip"    { return "[SKIP]" }
        "fail"    { return "[FAIL]" }
        "running" { return "[RUN ]" }
        "pending" { return "[    ]" }
        default   { return "[    ]" }
    }
}

function Get-StatusColor {
    param([string]$status)
    switch ($status) {
        "done"    { return "Green" }
        "skip"    { return "Yellow" }
        "fail"    { return "Red" }
        "running" { return "Cyan" }
        default   { return "DarkGray" }
    }
}

$startTime = Get-Date
$lastPhase = 0
$lastTask  = ""

Write-Host ""
Write-Host "  Waiting for setup_ros2_windows.ps1 to start..." -ForegroundColor DarkGray
Write-Host "  Progress file: $PROGRESS_FILE" -ForegroundColor DarkGray
Write-Host ""

while ($true) {
    # Read progress
    $progress = $null
    if (Test-Path $PROGRESS_FILE) {
        try {
            $raw = Get-Content $PROGRESS_FILE -Raw -ErrorAction SilentlyContinue
            $progress = $raw | ConvertFrom-Json
        } catch {}
    }

    # Compute overall %
    $overallDone = 0
    $totalTasks  = ($PHASES | Measure-Object -Property Total -Sum).Sum
    if ($progress) {
        foreach ($ph in $PHASES) {
            if ($progress.phase_num -gt $ph.Num) { $overallDone += $ph.Total }
            elseif ($progress.phase_num -eq $ph.Num) { $overallDone += $progress.task_num }
        }
    }
    $overallPct = if ($totalTasks -gt 0) { [math]::Round($overallDone / $totalTasks * 100) } else { 0 }
    $elapsed    = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 1)

    # Clear and redraw
    Clear-Host
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Magenta
    Write-Host "   Swachh Boudhik Yantra -- ROS 2 Setup Monitor" -ForegroundColor Magenta
    Write-Host "   Elapsed: ${elapsed} min   |   Press Ctrl+C to exit monitor" -ForegroundColor DarkGray
    Write-Host "  ============================================================" -ForegroundColor Magenta
    Write-Host ""

    # Overall bar
    $overallBar = Draw-Bar $overallPct 40
    Write-Host ("  OVERALL  " + $overallBar + "  $overallPct%") -ForegroundColor White
    Write-Host ""

    # Per-phase bars
    foreach ($ph in $PHASES) {
        $s = Get-PhaseStatus $ph.Num $progress
        $bar   = Draw-Bar $s.pct 28
        $icon  = Get-StatusIcon $s.status $s.pct
        $color = Get-StatusColor $s.status
        $label = ("Phase $($ph.Num)/6  " + $ph.Name).PadRight(24)
        $line  = "  $icon  $label $bar  $($s.pct)%"
        Write-Host $line -ForegroundColor $color
        if ($s.status -eq "running" -and $s.task -ne "") {
            Write-Host ("         --> " + $s.task) -ForegroundColor DarkGray
            if ($s.detail -ne "") {
                Write-Host ("             " + $s.detail) -ForegroundColor DarkGray
            }
        }
    }

    Write-Host ""

    # Current status detail
    if ($progress) {
        $statusLine = "  Current: Phase $($progress.phase_num) -- $($progress.task_name)"
        if ($progress.detail) { $statusLine += " [$($progress.detail)]" }
        Write-Host $statusLine -ForegroundColor Cyan
        Write-Host "  Updated: $($progress.timestamp)" -ForegroundColor DarkGray
    } else {
        Write-Host "  Waiting for setup script to start..." -ForegroundColor DarkGray
        Write-Host "  Make sure setup_ros2_windows.ps1 is running as Admin" -ForegroundColor Yellow
    }

    # Check if done
    if ($progress -and $progress.phase_num -eq 6 -and $progress.task_num -ge 3) {
        Write-Host ""
        Write-Host "  ============================================================" -ForegroundColor Green
        Write-Host "   ALL DONE! ROS 2 Humble + Nav2 installed successfully!" -ForegroundColor Green
        Write-Host "   Source env: . C:\dev\source_ros2.ps1" -ForegroundColor Green
        Write-Host "  ============================================================" -ForegroundColor Green
        break
    }

    Start-Sleep -Seconds 3
}

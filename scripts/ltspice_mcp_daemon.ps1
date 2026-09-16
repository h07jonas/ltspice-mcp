<#
.SYNOPSIS
  Windows PowerShell equivalent of scripts/ltspice_mcp_daemon.sh.

.DESCRIPTION
  Starts/stops/monitors the ltspice-mcp daemon (HTTP mode via `uv run ltspice-mcp --daemon-http`)
  as a background Windows process. Mirrors the bash daemon script's start/stop/status/restart/logs
  behavior described in README.md's "Daemon Operations" section.

  The macOS-only permission-trigger subcommands (trigger-initial-permissions,
  check-accessibility, trigger-accessibility-permission, trigger-screen-recording-permission)
  are NOT implemented here: Windows has no equivalent Accessibility/Screen-Recording consent
  dialogs to trigger, so there is nothing to port for those. `Get-Help` on this script explains
  this instead of faking a no-op implementation.

.PARAMETER Command
  One of: start, stop, restart, status, logs.

.EXAMPLE
  ./scripts/ltspice_mcp_daemon.ps1 start
.EXAMPLE
  ./scripts/ltspice_mcp_daemon.ps1 logs -Lines 200
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "help")]
    [string]$Command,

    [int]$Lines = 120,

    [switch]$Follow
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$DefaultWorkdir = Join-Path $ProjectRoot ".mcp-workdir"
$DaemonDir = if ($env:LTSPICE_MCP_DAEMON_DIR) { $env:LTSPICE_MCP_DAEMON_DIR } else { Join-Path $DefaultWorkdir "daemon" }
$LogDir = Join-Path $DaemonDir "logs"
$PidFile = Join-Path $DaemonDir "ltspice-mcp-daemon.pid"

$HostName = if ($env:LTSPICE_MCP_DAEMON_HOST) { $env:LTSPICE_MCP_DAEMON_HOST } else { "127.0.0.1" }
$Port = if ($env:LTSPICE_MCP_DAEMON_PORT) { $env:LTSPICE_MCP_DAEMON_PORT } else { "8765" }
$HttpPath = if ($env:LTSPICE_MCP_DAEMON_HTTP_PATH) { $env:LTSPICE_MCP_DAEMON_HTTP_PATH } else { "/mcp" }
if ($HttpPath -notlike "/*") { $HttpPath = "/$HttpPath" }
$Workdir = if ($env:LTSPICE_MCP_DAEMON_WORKDIR) { $env:LTSPICE_MCP_DAEMON_WORKDIR } else { $DefaultWorkdir }
$Timeout = if ($env:LTSPICE_MCP_DAEMON_TIMEOUT) { $env:LTSPICE_MCP_DAEMON_TIMEOUT } else { "180" }
$LtspiceBinary = if ($env:LTSPICE_MCP_DAEMON_LTSPICE_BINARY) { $env:LTSPICE_MCP_DAEMON_LTSPICE_BINARY } else { "" }
$UvBin = if ($env:UV_BIN) { $env:UV_BIN } else { "uv" }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-DaemonUrl {
    "http://${HostName}:${Port}${HttpPath}"
}

function Get-PidFromFile {
    if (-not (Test-Path $PidFile)) { return $null }
    $raw = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($raw -match '^\d+$') { return [int]$raw }
    return $null
}

function Test-ProcessAlive([int]$ProcId) {
    if (-not $ProcId) { return $false }
    return $null -ne (Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

function Get-LatestLogPath {
    $latest = Get-ChildItem -Path $LogDir -Filter "ltspice-mcp-daemon-*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return $null
}

function Test-DaemonRunning {
    $procId = Get-PidFromFile
    if ($procId -and (Test-ProcessAlive $procId)) { return $procId }
    return $null
}

function Start-Daemon {
    $running = Test-DaemonRunning
    if ($running) {
        Write-Host "ltspice-mcp daemon already running (pid $running)"
        Write-Host "URL: $(Get-DaemonUrl)"
        return
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logFile = Join-Path $LogDir "ltspice-mcp-daemon-$timestamp.log"

    $argList = @(
        "run", "--project", $ProjectRoot, "ltspice-mcp",
        "--daemon-http",
        "--host", $HostName,
        "--port", $Port,
        "--http-path", $HttpPath,
        "--workdir", $Workdir,
        "--timeout", $Timeout
    )
    if ($LtspiceBinary) {
        $argList += @("--ltspice-binary", $LtspiceBinary)
    }

    $process = Start-Process -FilePath $UvBin -ArgumentList $argList `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError "$logFile.err" `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -Path $PidFile -Value $process.Id

    Start-Sleep -Milliseconds 500
    if (-not (Test-ProcessAlive $process.Id)) {
        Write-Error "Failed to start daemon. Recent log output:"
        if (Test-Path $logFile) { Get-Content $logFile -Tail 120 }
        if (Test-Path "$logFile.err") { Get-Content "$logFile.err" -Tail 120 }
        Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
        exit 1
    }

    Write-Host "Started ltspice-mcp daemon (pid $($process.Id))"
    Write-Host "URL: $(Get-DaemonUrl)"
    Write-Host "Log: $logFile"
}

function Stop-Daemon {
    $procId = Get-PidFromFile
    if (-not $procId -or -not (Test-ProcessAlive $procId)) {
        Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
        Write-Host "ltspice-mcp daemon is not running"
        return
    }

    Stop-Process -Id $procId -ErrorAction SilentlyContinue
    $tries = 0
    while ($tries -lt 40 -and (Test-ProcessAlive $procId)) {
        Start-Sleep -Milliseconds 250
        $tries++
    }
    if (Test-ProcessAlive $procId) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
        Write-Host "Force-stopped ltspice-mcp daemon"
    } else {
        Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
        Write-Host "Stopped ltspice-mcp daemon"
    }
}

function Get-Status {
    $procId = Test-DaemonRunning
    if ($procId) {
        Write-Host "ltspice-mcp daemon: running (pid $procId)"
        Write-Host "URL: $(Get-DaemonUrl)"
        $logFile = Get-LatestLogPath
        if ($logFile) { Write-Host "Latest log: $logFile" }
    } else {
        Write-Host "ltspice-mcp daemon: not running"
        Write-Host "URL: $(Get-DaemonUrl)"
        exit 1
    }
}

function Show-Logs {
    $logFile = Get-LatestLogPath
    if (-not $logFile) {
        Write-Error "No daemon log file found in $LogDir"
        exit 1
    }
    if ($Follow) {
        Get-Content -Path $logFile -Tail $Lines -Wait
    } else {
        Get-Content -Path $logFile -Tail $Lines
    }
}

function Show-Help {
    Write-Host @"
Usage: ./scripts/ltspice_mcp_daemon.ps1 <command> [options]

Commands:
  start                 Start the LTspice MCP daemon (HTTP mode via uv)
  stop                  Stop the daemon
  restart               Restart the daemon
  status                Print daemon status
  logs [-Lines N] [-Follow]
                         Print (or follow) latest daemon log output (default: 120 lines)

NOT implemented on Windows (no equivalent exists):
  trigger-initial-permissions, check-accessibility,
  trigger-accessibility-permission, trigger-screen-recording-permission
    These trigger macOS Accessibility/Screen-Recording consent dialogs.
    Windows has no such consent system for this server's UI-automation
    and window-capture features, so there is nothing to port here.

Environment overrides:
  LTSPICE_MCP_DAEMON_HOST, LTSPICE_MCP_DAEMON_PORT, LTSPICE_MCP_DAEMON_HTTP_PATH,
  LTSPICE_MCP_DAEMON_WORKDIR, LTSPICE_MCP_DAEMON_TIMEOUT, LTSPICE_MCP_DAEMON_LTSPICE_BINARY,
  LTSPICE_MCP_DAEMON_DIR, UV_BIN
"@
}

switch ($Command) {
    "start"   { Start-Daemon }
    "stop"    { Stop-Daemon }
    "restart" { Stop-Daemon; Start-Daemon }
    "status"  { Get-Status }
    "logs"    { Show-Logs }
    "help"    { Show-Help }
    default   { Show-Help }
}

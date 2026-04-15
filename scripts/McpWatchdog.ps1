# McpWatchdog.ps1 — separate elevated supervisor: TCP check on loopback, kill tree, restart MCP.
# Run from elevated PowerShell, or without admin: script re-launches itself via RunAs (UAC once).
# Encoding: UTF-8 with BOM recommended on disk for Cyrillic in logs under Windows PowerShell 5.1.
#
# Example (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\McpWatchdog.ps1 -McpRoot "C:\path\to\map_win_server_clicker"
#
# Stops only python.exe / pythonw.exe whose CommandLine contains this clone's src\server.py (resolved path).

[CmdletBinding()]
param(
    [string]$McpRoot = "",
    [int]$PollSeconds = 10,
    [int]$Port = 0,
    [int]$TcpTimeoutMs = 2500,
    [int]$PortFailThreshold = 3,
    [switch]$SkipElevation
)

$ErrorActionPreference = "Stop"

function Test-WdAdmin {
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not $SkipElevation) {
    if (-not (Test-WdAdmin)) {
        $self = $PSCommandPath
        if (-not (Test-Path -LiteralPath $self)) {
            throw "Cannot resolve script path for elevation."
        }
        $mr = $McpRoot.Trim()
        if ([string]::IsNullOrWhiteSpace($mr)) {
            $mr = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
        }
        else {
            $mr = (Resolve-Path -LiteralPath $mr).Path
        }
        $argList = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $self,
            "-SkipElevation",
            "-McpRoot", $mr,
            "-PollSeconds", "$PollSeconds",
            "-PortFailThreshold", "$PortFailThreshold",
            "-TcpTimeoutMs", "$TcpTimeoutMs"
        )
        if ($Port -gt 0) {
            $argList += "-Port"
            $argList += "$Port"
        }
        Start-Process -FilePath "powershell.exe" -ArgumentList $argList -Verb RunAs | Out-Null
        Write-Host "Requested elevation (UAC). Watchdog starts in a new elevated window."
        exit 0
    }
}

if ([string]::IsNullOrWhiteSpace($McpRoot)) {
    $McpRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
else {
    $McpRoot = (Resolve-Path -LiteralPath $McpRoot.Trim()).Path
}

if ($Port -le 0) {
    $raw = $env:MCP_PORT
    if ($raw -match "^\d+$") {
        $Port = [int]$raw
    }
    else {
        $Port = 8765
    }
}

$venvPython = Join-Path $McpRoot ".venv\Scripts\python.exe"
$serverPy = Join-Path $McpRoot "src\server.py"
if (-not (Test-Path -LiteralPath $serverPy)) {
    throw "server.py not found: $serverPy"
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "venv python not found: $venvPython (run setup_local.ps1)"
}

$serverPyResolved = (Resolve-Path -LiteralPath $serverPy).Path
$needle = $serverPyResolved.ToLowerInvariant()

$logDir = Join-Path $McpRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "mcp_watchdog.log"

function Write-WdLog([string]$msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') $msg"
    try {
        Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    }
    catch { }
    Write-Host $line
}

function Test-WdPortOpen {
    param([int]$PortNum, [int]$TimeoutMs)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect([System.Net.IPAddress]::Loopback, $PortNum, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    }
    catch {
        return $false
    }
    finally {
        try { $client.Close() } catch { }
    }
}

function Stop-WdMcpPythonProcesses {
    $names = @("python.exe", "pythonw.exe")
    foreach ($n in $names) {
        $list = @(Get-CimInstance Win32_Process -Filter "Name='$n'" -ErrorAction SilentlyContinue)
        foreach ($wp in $list) {
            $cl = $wp.CommandLine
            if (-not $cl) { continue }
            if ($cl.ToLowerInvariant().Contains($needle)) {
                Write-WdLog "taskkill /T /F PID=$($wp.ProcessId) ($n)"
                $null = & taskkill.exe /PID $wp.ProcessId /T /F 2>&1
            }
        }
    }
}

function Start-WdMcpServer {
    $pipCache = Join-Path $McpRoot ".pip-cache"
    $tmpDir = Join-Path $McpRoot ".tmp"
    New-Item -ItemType Directory -Force -Path $pipCache | Out-Null
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    $env:PIP_CACHE_DIR = $pipCache
    $env:TMP = $tmpDir
    $env:TEMP = $tmpDir
    if ([string]::IsNullOrWhiteSpace($env:MCP_ALLOW_SELF_UPDATE)) {
        $env:MCP_ALLOW_SELF_UPDATE = "1"
    }
    Write-WdLog "Start-Process $venvPython $serverPyResolved (cwd=$McpRoot)"
    Start-Process -FilePath $venvPython -ArgumentList "`"$serverPyResolved`"" -WorkingDirectory $McpRoot -WindowStyle Minimized | Out-Null
}

Write-WdLog "McpWatchdog started (admin=$(Test-WdAdmin) McpRoot=$McpRoot Port=$Port Poll=${PollSeconds}s threshold=$PortFailThreshold)"
$consecutive = 0
while ($true) {
    try {
        if (Test-WdPortOpen -PortNum $Port -TimeoutMs $TcpTimeoutMs) {
            if ($consecutive -gt 0) {
                Write-WdLog "port $Port reachable again"
            }
            $consecutive = 0
        }
        else {
            $consecutive++
            Write-WdLog "port $Port not reachable ($consecutive / $PortFailThreshold)"
            if ($consecutive -ge $PortFailThreshold) {
                Stop-WdMcpPythonProcesses
                Start-Sleep -Seconds 2
                Start-WdMcpServer
                $consecutive = 0
                Start-Sleep -Seconds 5
            }
        }
    }
    catch {
        Write-WdLog "loop error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $PollSeconds
}

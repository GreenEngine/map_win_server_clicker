# Run MCP from local .venv; pip cache and TEMP in project folder (same as setup_local.ps1).
# (ASCII messages: compatible with Windows PowerShell 5.x without UTF-8 BOM.)
#
# Example:
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
# Disable self-update (server_update tool will be forbidden):
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -NoSelfUpdate

param(
    [switch]$NoSelfUpdate = $false,
    [switch]$AllowLaunch = $false
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")

if (-not $NoSelfUpdate -and [string]::IsNullOrWhiteSpace($env:MCP_ALLOW_SELF_UPDATE)) {
    $env:MCP_ALLOW_SELF_UPDATE = "1"
}

if ($AllowLaunch) {
    $env:MCP_ALLOW_LAUNCH = "1"
}

$pipCache = Join-Path $ProjectRoot ".pip-cache"
$tmpDir = Join-Path $ProjectRoot ".tmp"
New-Item -ItemType Directory -Force -Path $pipCache | Out-Null
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

$env:PIP_CACHE_DIR = $pipCache
$env:TMP = $tmpDir
$env:TEMP = $tmpDir

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "No .venv found. Run first: powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1"
}

Push-Location $ProjectRoot
try {
    & $venvPython (Join-Path $ProjectRoot "src\server.py")
}
finally {
    Pop-Location
}

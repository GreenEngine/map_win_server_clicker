# Запуск MCP из локального .venv; кэш pip и TEMP — в папке проекта (как в setup_local.ps1).
#
# Пример:
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
# Без self-update (инструмент server_update в MCP будет отключён):
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -NoSelfUpdate

param(
    # По умолчанию разрешаем server_update из MCP, если переменная ещё не задана снаружи.
    [switch]$NoSelfUpdate = $false,
    # Разрешить инструмент launch_process (запуск .exe с машины через MCP).
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
    throw "Нет .venv. Сначала: powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1"
}

Push-Location $ProjectRoot
try {
    & $venvPython (Join-Path $ProjectRoot "src\server.py")
}
finally {
    Pop-Location
}

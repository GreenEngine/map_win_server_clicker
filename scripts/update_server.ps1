# Обновление MCP на Windows: git pull (опционально) + pip install.
# Вызывается вручную или из server_update при MCP_ALLOW_SELF_UPDATE=1.
#
# Параметры:
#   -RepoRoot       корень git (по умолчанию: .git внутри windows-mcp-server, иначе .git у родителя — монорепо)
#   -SkipGit        не выполнять git pull
#
# Перезапуск процесса MCP после обновления выполняет Python (update.schedule_restart_after_update),
# а не этот скрипт — так надёжнее на всех вариантах запуска Cursor/venv.
#
# Пример:
#   powershell -ExecutionPolicy Bypass -File scripts/update_server.ps1 -RepoRoot D:\LEP

param(
    [string]$RepoRoot = "",
    [switch]$SkipGit = $false
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$mcpRoot = Resolve-Path (Join-Path $here "..")
if (-not $RepoRoot) {
    $parent = Split-Path $mcpRoot -Parent
    if (Test-Path (Join-Path $mcpRoot ".git")) {
        $RepoRoot = $mcpRoot.Path
    } elseif ($parent -and (Test-Path (Join-Path $parent ".git"))) {
        $RepoRoot = $parent
    } else {
        $RepoRoot = $mcpRoot.Path
    }
}
Write-Host "MCP root: $mcpRoot"
Write-Host "Repo root: $RepoRoot"

if (-not $SkipGit -and (Test-Path (Join-Path $RepoRoot ".git"))) {
    Push-Location $RepoRoot
    try {
        git pull --ff-only
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Git pull skipped."
}

$req = Join-Path $mcpRoot "requirements.txt"
$venvPy = Join-Path $mcpRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $pipCache = Join-Path $mcpRoot ".pip-cache"
    $tmpDir = Join-Path $mcpRoot ".tmp"
    New-Item -ItemType Directory -Force -Path $pipCache -ErrorAction SilentlyContinue | Out-Null
    New-Item -ItemType Directory -Force -Path $tmpDir -ErrorAction SilentlyContinue | Out-Null
    $env:PIP_CACHE_DIR = $pipCache
    $env:TMP = $tmpDir
    $env:TEMP = $tmpDir
    & $venvPy -m pip install -r $req
}
else {
    python -m pip install -r $req
}

Write-Host "Done. MCP process restart is scheduled by server_update (Python), not by this script."

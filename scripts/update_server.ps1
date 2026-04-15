# Обновление MCP на Windows: git pull (опционально) + pip install.
# Вызывается вручную или из server_update при MCP_ALLOW_SELF_UPDATE=1.
#
# Параметры:
#   -RepoRoot       корень git (по умолчанию: .git внутри windows-mcp-server, иначе .git у родителя — монорепо)
#   -SkipGit        не выполнять git pull
#   -McpParentPid   PID текущего процесса MCP (передаёт server_update); если > 0 — после pip стартует перезапуск
#   -PythonExe      интерпретатор Python для mcp_restart_after_update.py (тот же, что у процесса MCP)
#
# Пример:
#   powershell -ExecutionPolicy Bypass -File scripts/update_server.ps1 -RepoRoot D:\LEP

param(
    [string]$RepoRoot = "",
    [switch]$SkipGit = $false,
    [int]$McpParentPid = 0,
    [string]$PythonExe = ""
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

$mcpRootPath = if ($mcpRoot.Path) { $mcpRoot.Path } else { "$mcpRoot" }
$helper = Join-Path $mcpRootPath "scripts\mcp_restart_after_update.py"
$serverPy = Join-Path $mcpRootPath "src\server.py"

if ($McpParentPid -gt 0 -and $PythonExe -and (Test-Path $helper) -and (Test-Path $serverPy)) {
    Write-Host "Starting MCP restart helper (parent PID $McpParentPid) via PowerShell..."
    try {
        Start-Process `
            -FilePath $PythonExe `
            -ArgumentList @($helper, "$McpParentPid", $PythonExe, $serverPy, $mcpRootPath) `
            -WorkingDirectory $mcpRootPath `
            -WindowStyle Hidden `
            -ErrorAction Stop
        Write-Host "Restart helper started; MCP parent process should exit shortly (see server_update log)."
    }
    catch {
        Write-Error "Failed to start MCP restart helper: $_"
        throw
    }
}
else {
    Write-Host "Done. Restart the MCP server process manually to load new Python files (no -McpParentPid/-PythonExe or helper missing)."
}

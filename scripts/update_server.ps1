# Обновление MCP на Windows: git (опционально, см. ниже) + pip install.
# Из server_update на Windows скрипт вызывается с -SkipGit: git для git_pull/full делает Python (fetch + pull --ff-only origin/<ветка>).
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
        git fetch origin
        $branch = (git rev-parse --abbrev-ref HEAD).Trim()
        if (-not $branch) { $branch = "main" }
        function Test-OriginRef([string]$name) {
            git show-ref --verify "refs/remotes/origin/$name" 2>$null | Out-Null
            return ($LASTEXITCODE -eq 0)
        }
        $remoteDefault = ""
        $sym = git symbolic-ref -q refs/remotes/origin/HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $sym -match "refs/remotes/origin/(.+)$") {
            $remoteDefault = $Matches[1].Trim()
        }
        $target = ""
        if (($branch -eq "master" -or $branch -eq "main") -and $remoteDefault -and (Test-OriginRef $remoteDefault) -and $remoteDefault -ne $branch) {
            $target = $remoteDefault
            Write-Host "Git pull target from origin/HEAD: $target (local branch $branch)"
        } else {
            foreach ($b in @($branch, "main", "master")) {
                if (Test-OriginRef $b) { $target = $b; break }
            }
        }
        if ($target) {
            git pull --ff-only origin $target
        } else {
            git pull --ff-only
        }
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

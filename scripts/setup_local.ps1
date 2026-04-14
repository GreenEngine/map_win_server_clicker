# Install deps into project: .venv, .pip-cache, .tmp. Optional: embeddable Python in .\python-embed\
# (ASCII messages: compatible with Windows PowerShell 5.x without UTF-8 BOM.)
#
# Examples:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1 -DownloadEmbed
#   powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1 -PythonExe "D:\Python312\python.exe"

param(
    [string]$PythonExe = "",
    [switch]$DownloadEmbed = $false,
    [string]$EmbedVersion = "3.12.7"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")

$pipCache = Join-Path $ProjectRoot ".pip-cache"
$tmpDir = Join-Path $ProjectRoot ".tmp"
New-Item -ItemType Directory -Force -Path $pipCache | Out-Null
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

$env:PIP_CACHE_DIR = $pipCache
$env:TMP = $tmpDir
$env:TEMP = $tmpDir

$embedRoot = Join-Path $ProjectRoot "python-embed"

function Install-EmbedPython {
    param([string]$Ver)
    $zipName = "python-$Ver-embed-amd64.zip"
    $url = "https://www.python.org/ftp/python/$Ver/$zipName"
    $zipPath = Join-Path $tmpDir $zipName

    Write-Host "Downloading embeddable Python $Ver to $embedRoot ..."
    if (Test-Path $embedRoot) {
        Remove-Item -Recurse -Force $embedRoot
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    New-Item -ItemType Directory -Force -Path $embedRoot | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $embedRoot -Force
    Remove-Item -Force $zipPath -ErrorAction SilentlyContinue

    $pth = Get-ChildItem -Path $embedRoot -Filter "python*._pth" | Select-Object -First 1
    if (-not $pth) {
        throw "python*._pth not found under $embedRoot"
    }
    $txt = Get-Content -Raw -Path $pth.FullName
    $txt = $txt -replace "#\s*import site", "import site"
    $txt = $txt -replace "#import site", "import site"
    Set-Content -Path $pth.FullName -Value $txt -NoNewline

    $py = Join-Path $embedRoot "python.exe"
    Write-Host "ensurepip / pip ..."
    & $py -m ensurepip --upgrade 2>&1 | Out-Null
    $pipOk = Test-Path (Join-Path $embedRoot "Scripts\pip.exe")
    if (-not $pipOk) {
        $gp = Join-Path $tmpDir "get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $gp -UseBasicParsing
        & $py $gp --no-warn-script-location
    }
    Write-Host "Embeddable ready: $py"
}

if ($DownloadEmbed) {
    Install-EmbedPython -Ver $EmbedVersion
}

if (-not $PythonExe) {
    if ($env:MCP_PYTHON) {
        $PythonExe = $env:MCP_PYTHON
    }
    elseif (Test-Path (Join-Path $embedRoot "python.exe")) {
        $PythonExe = Join-Path $embedRoot "python.exe"
    }
    else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $PythonExe = $cmd.Source }
    }
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw @'
Python not found.
  Option 1: powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1 -DownloadEmbed
  Option 2: -PythonExe "C:\full\path\python.exe"
  Option 3: install Python and set env MCP_PYTHON
'@
}

Write-Host "Using: $PythonExe"
Write-Host "PIP_CACHE_DIR=$pipCache"
Write-Host "TEMP/TMP=$tmpDir"

$venvPath = Join-Path $ProjectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating venv: $venvPath"
    & $PythonExe -m venv $venvPath
}

& $venvPython -m pip install --upgrade pip
$req = Join-Path $ProjectRoot "requirements.txt"
& $venvPython -m pip install -r $req

Write-Host ""
Write-Host "Done. Start server: .\scripts\run_local.ps1"
Write-Host "Or: .\.venv\Scripts\python.exe src\server.py"

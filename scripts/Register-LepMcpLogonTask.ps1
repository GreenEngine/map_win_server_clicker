# Register-LepMcpLogonTask.ps1
# Scheduled task: MCP server at user logon + restart on failure (interactive session for nanoCAD UIA).
# See docs/WINDOWS_AUTOSTART.md
# Encoding: UTF-8 with BOM; body ASCII-only for Windows PowerShell 5.1.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $McpRoot,
    [string] $PythonExe = "",
    [string] $TaskName = "LEP-Windows-MCP"
)

$ErrorActionPreference = "Stop"
$McpRoot = $McpRoot.Trim().TrimEnd('\').TrimEnd('/')

if (-not (Test-Path -LiteralPath $McpRoot)) {
    $hint = ""
    if ($McpRoot -match 'map_min_server_clicker') {
        $alt = $McpRoot -replace 'map_min_server_clicker', 'map_win_server_clicker'
        if (Test-Path -LiteralPath $alt) {
            $hint = " Similar path exists (typo min->win): $alt Use it as -McpRoot."
        } else {
            $hint = " Check typo: folder name is map_win_server_clicker (not map_min_server_clicker)."
        }
    }
    throw "Directory not found: $McpRoot $hint Pass -McpRoot to repo root (folder containing src\server.py)."
}

$McpRoot = (Resolve-Path -LiteralPath $McpRoot).Path

if (-not $PythonExe) {
    $PythonExe = Join-Path $McpRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python not found: $PythonExe Create venv or pass -PythonExe."
}

$ServerPy = Join-Path $McpRoot "src\server.py"
if (-not (Test-Path -LiteralPath $ServerPy)) {
    throw "server.py not found: $ServerPy"
}

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ServerPy`"" -WorkingDirectory $McpRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Write-Host "OK: registered task '$TaskName' (AtLogOn user=$env:USERNAME RestartCount=3)."
Write-Host "Check: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"

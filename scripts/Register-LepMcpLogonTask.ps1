<#
.SYNOPSIS
  Регистрирует задачу планировщика: LEP Windows MCP при входе пользователя + перезапуск при сбое.

.DESCRIPTION
  Не использует классическую службу LocalSystem — MCP должен работать в интерактивной сессии
  того же пользователя, что и nanoCAD (см. docs/WINDOWS_AUTOSTART.md).

  Запуск: PowerShell от имени администратора (опционально), при необходимости поправьте пути.

.PARAMETER McpRoot
  Каталог windows-mcp-server (где лежат src\, scripts\, .venv\).

.PARAMETER PythonExe
  Полный путь к python.exe (по умолчанию: McpRoot\.venv\Scripts\python.exe).

.PARAMETER TaskName
  Имя задачи в планировщике (по умолчанию: LEP-Windows-MCP).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $McpRoot,
    [string] $PythonExe = "",
    [string] $TaskName = "LEP-Windows-MCP"
)

$ErrorActionPreference = "Stop"
$McpRoot = (Resolve-Path -LiteralPath $McpRoot).Path
if (-not $PythonExe) {
    $PythonExe = Join-Path $McpRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python не найден: $PythonExe (создайте venv или укажите -PythonExe)"
}
$ServerPy = Join-Path $McpRoot "src\server.py"
if (-not (Test-Path -LiteralPath $ServerPy)) {
    throw "Не найден server.py: $ServerPy"
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
Write-Host "OK: зарегистрирована задача '$TaskName' (AtLogOn, user=$env:USERNAME, RestartCount=3)."
Write-Host "Проверка: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"

<#
.SYNOPSIS
  Регистрирует задачу планировщика: LEP Windows MCP при входе пользователя + перезапуск при сбое.

.DESCRIPTION
  Не использует классическую службу LocalSystem — MCP должен работать в интерактивной сессии
  того же пользователя, что и nanoCAD (см. docs/WINDOWS_AUTOSTART.md).

  Запуск: PowerShell от имени администратора (опционально), при необходимости поправьте пути.

.PARAMETER McpRoot
  Корень репозитория на диске (каталог, где лежат src\, scripts\, .venv\) — например
  C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker
  (не родитель Desktop\windows-mcp-server без вложенной папки клона, и без опечатки map_min → map_win).

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
$McpRoot = $McpRoot.Trim().TrimEnd('\', '/')
if (-not (Test-Path -LiteralPath $McpRoot)) {
    $hint = ""
    if ($McpRoot -match 'map_min_server_clicker') {
        $alt = $McpRoot -replace 'map_min_server_clicker', 'map_win_server_clicker'
        if (Test-Path -LiteralPath $alt) {
            $hint = " Найден похожий путь (опечатка min→win): $alt — используйте его в -McpRoot."
        } else {
            $hint = " Проверьте опечатку: часто нужно map_win_server_clicker, а не map_min_server_clicker."
        }
    }
    throw "Каталог не существует: $McpRoot.$hint Укажите -McpRoot на корень клона (где есть src\server.py)."
}
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

# Автозапуск и перезапуск MCP на Windows

## Почему после `server_update` процесс «не поднялся»

Встроенный перезапуск делает отдельный процесс [`scripts/mcp_restart_after_update.py`](../scripts/mcp_restart_after_update.py): ждёт завершения старого PID, **ждёт освобождения TCP-порта** (`MCP_HOST` / `MCP_PORT`), затем снова запускает `src/server.py`. Если нового процесса нет:

1. Откройте **`windows-mcp-server/logs/mcp_restart_helper.log`** — шаги helper и ошибки `Popen`.
2. Откройте **`windows-mcp-server/logs/mcp_server_stderr.log`** — stderr нового сервера (если файл удалось создать).
3. Убедитесь, что порт **8765** (или ваш `MCP_PORT`) не занят другим приложением.
4. Переменная **`MCP_RESTART_LOG`** (необязательно) — явный путь к логу helper вместо `logs/mcp_restart_helper.log`.

## Классическая «служба Windows» (LocalSystem) и UI с nanoCAD

Служба, запущенная как **LocalSystem** без интерактивной сессии пользователя, **часто не видит** окна nanoCAD на рабочем столе пользователя (изоляция сессий, Session 0). **UIA-палитра LEP** в типичной схеме QA требует, чтобы MCP работал **в той же интерактивной сессии**, что и nanoCAD (пользователь залогинен по RDP/локально).

Поэтому для LEP рекомендуется не «чистый» `sc create` под SYSTEM, а один из вариантов ниже.

## Рекомендуемый вариант: задача планировщика при входе пользователя

Скрипт (**обязательно PowerShell от имени администратора** — иначе `Register-ScheduledTask` даст **Access denied / 0x80070005** из‑за `RunLevel Highest`); **`-McpRoot`** — каталог **клона**, где лежат `src\` и `.venv\`, например `C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker`, а не опечатка `map_min_server_clicker`):

[`scripts/Register-LepMcpLogonTask.ps1`](../scripts/Register-LepMcpLogonTask.ps1)

```powershell
cd C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker
.\scripts\Register-LepMcpLogonTask.ps1 -McpRoot "C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker"
```

Если PowerShell выдаёт **ParserError** с «кракозябрами» (например `Ð...`) и ссылается на строки вроде 37/68 с русским текстом в ошибке — на диске **старая копия** скрипта (UTF-8 без BOM и кириллица читались как ANSI). В каталоге клона выполните **`git pull`**, откройте `scripts\Register-LepMcpLogonTask.ps1` и проверьте, что это **короткий** файл (~58 строк), сообщения об ошибках **на английском**, файл сохранён как **UTF-8 с BOM**.

Если видите **`Register-ScheduledTask : Access is denied`** (HRESULT **0x80070005**) — запустите **Windows PowerShell** или **Terminal** через контекстное меню **«Запуск от имени администратора»** и снова выполните скрипт. Сообщение **OK** после ошибки в старых версиях скрипта было вводящим в заблуждение; в актуальной версии при отказе в доступе скрипт завершается сразу после неудачной регистрации.

- Триггер: **вход в систему** выбранного пользователя.
- Поведение: **только при входе пользователя** (не «в фоне без входа») — сохраняется доступ к столу для UIA.
- При сбое задачи: **перезапуск** (до 3 раз с интервалом) — если процесс MCP упал, планировщик поднимет его снова после сбоя.

После правки кода на ВМ по-прежнему можно вызывать **`server_update`**; helper перезапуска дополняет (или заменяет при ручном старте) механизм планировщика.

## Альтернатива: NSSM

[Non-Sucking Service Manager (NSSM)](https://nssm.cc/) оборачивает `python.exe …\src\server.py` в службу. Обязательно укажите **учётную запись того же пользователя**, под которым открывают nanoCAD, и отметьте взаимодействие с рабочим столом (зависит от версии Windows / политик). Иначе UIA снова будет «пустым».

## Сторож MCP (отдельный процесс, перезапуск при «мёртвом» порте)

Если сервер **завис**, но процесс ещё жив, проверка **TCP на 127.0.0.1** может оставаться успешной — тогда сторож **не** перезапустит (это ограничение «порта как пробы»). Для типичного случая **процесс умер / порт не слушается** — достаточно.

Скрипт [`scripts/McpWatchdog.ps1`](../scripts/McpWatchdog.ps1):

- при запуске **без** прав администратора один раз запросит **UAC** и откроет новое окно PowerShell **от имени администратора**;
- в цикле проверяет порт (`MCP_PORT` или **8765**); после **нескольких** подряд неудач завершает дерево процессов `python.exe`/`pythonw.exe`, у которых в командной строке есть **полный путь** к `src\server.py` **этого** клона, и снова запускает сервер (те же каталоги `.pip-cache` / `.tmp`, что и `run_local.ps1`);
- пишет строки в **`logs/mcp_watchdog.log`** и дублирует в консоль.

Пример:

```powershell
cd C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker
powershell -ExecutionPolicy Bypass -File .\scripts\McpWatchdog.ps1 -McpRoot "C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker"
```

Параметры: `-PollSeconds`, `-Port`, `-TcpTimeoutMs`, `-PortFailThreshold` (сколько неудачных проверок порта подряд до kill+start). Окно сторожа > **один экземпляр на порт**.

Чтобы сторож поднимался после входа, зарегистрируйте вторую задачу планировщика (аналогично `Register-LepMcpLogonTask.ps1`): действие — `powershell.exe -ExecutionPolicy Bypass -File "...\scripts\McpWatchdog.ps1" -SkipElevation -McpRoot "..."` (для задачи уже под админом можно сразу `-SkipElevation`).

## Ручной перезапуск

Остановить процесс `python … server.py`, из каталога `windows-mcp-server` с активированным venv:

```text
python src\server.py
```

См. также [DEPLOY_VM_CHECKLIST.md](DEPLOY_VM_CHECKLIST.md).

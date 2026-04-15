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

Скрипт (запуск **от администратора** при необходимости; **`-McpRoot`** — каталог **клона**, где лежат `src\` и `.venv\`, например `C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker`, а не опечатка `map_min_server_clicker`):

[`scripts/Register-LepMcpLogonTask.ps1`](../scripts/Register-LepMcpLogonTask.ps1)

```powershell
cd C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker
.\scripts\Register-LepMcpLogonTask.ps1 -McpRoot "C:\Users\Admin\Desktop\windows-mcp-server\map_win_server_clicker"
```

- Триггер: **вход в систему** выбранного пользователя.
- Поведение: **только при входе пользователя** (не «в фоне без входа») — сохраняется доступ к столу для UIA.
- При сбое задачи: **перезапуск** (до 3 раз с интервалом) — если процесс MCP упал, планировщик поднимет его снова после сбоя.

После правки кода на ВМ по-прежнему можно вызывать **`server_update`**; helper перезапуска дополняет (или заменяет при ручном старте) механизм планировщика.

## Альтернатива: NSSM

[Non-Sucking Service Manager (NSSM)](https://nssm.cc/) оборачивает `python.exe …\src\server.py` в службу. Обязательно укажите **учётную запись того же пользователя**, под которым открывают nanoCAD, и отметьте взаимодействие с рабочим столом (зависит от версии Windows / политик). Иначе UIA снова будет «пустым».

## Ручной перезапуск

Остановить процесс `python … server.py`, из каталога `windows-mcp-server` с активированным venv:

```text
python src\server.py
```

См. также [DEPLOY_VM_CHECKLIST.md](DEPLOY_VM_CHECKLIST.md).

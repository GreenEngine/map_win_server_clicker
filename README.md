# LEP Windows MCP Server

Репозиторий на GitHub: **[GreenEngine/map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker)**.

MCP-сервер для **Windows Server / Windows 10+**: **Streamable HTTP**, инструменты **UI Automation** (pywinauto) для NanoCAD/плагина и других оконных приложений, плюс **`server_update`** — обновление кода/зависимостей на сервере по запросу агента (с флагом безопасности).

## Требования

- Windows, Python **3.10+**
- Запуск в **интерактивной пользовательской сессии** (тот же пользователь, под которым открыт NanoCAD / RDP-сеанс). Служба без стола обычно **не** подходит для UIA.
- Права на установку пакетов в выбранный venv.
- Скрипты **`scripts\*.ps1`** выводят сообщения **на английском**, чтобы **Windows PowerShell 5.1** не ломал разбор при **UTF-8 без BOM** (ошибка «missing terminator» на строках с кириллицей).

## Установка

**Всё в папке проекта** (venv `.venv`, кэш pip `.pip-cache`, временные файлы `.tmp`; при `-DownloadEmbed` ещё `python-embed\`):

```powershell
cd D:\path\to\LEP\windows-mcp-server
powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1 -DownloadEmbed
```

`-DownloadEmbed` скачивает [embeddable](https://www.python.org/downloads/windows/) в `python-embed\` (версию можно сменить: `-EmbedVersion "3.12.7"`). Если Python уже установлен:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1
# или с явным интерпретатором:
powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1 -PythonExe "C:\...\python.exe"
```

Запуск после установки:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```

Классический вариант вручную:

```powershell
cd D:\path\to\LEP\windows-mcp-server
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Разработка и тесты

Для локального прогона unit-тестов (без UIA): установите dev-зависимости и запустите pytest из каталога `windows-mcp-server` с `PYTHONPATH=.` (чтобы резолвился пакет `src`):

```bash
cd windows-mcp-server
pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=. pytest tests/ -q
```

### Автономный прогон сценария на Windows (без Cursor)

Скрипт **[scripts/execute_lep_scenario_local.py](scripts/execute_lep_scenario_local.py)** выполняет шаги из **`scenarios/*.json`**, вызывая функции инструментов из **`src/server.py`** в том же процессе Python (тот же venv). Это **не HTTP** к эндпоинту MCP, но даёт плановый прогон на ВМ в **интерактивной пользовательской сессии** рядом с nanoCAD без агента Cursor.

```powershell
cd D:\path\to\LEP\windows-mcp-server
.\.venv\Scripts\activate
$env:PYTHONPATH="."
python scripts/execute_lep_scenario_local.py --scenario scenarios/_template.json
```

Проверка JSON и белого списка `invoke` без импорта сервера (CI на macOS/Linux):

```bash
cd windows-mcp-server && PYTHONPATH=. python scripts/execute_lep_scenario_local.py --scenario scenarios/_template.json --validate-only
```

Markdown-промпт для чата: **`scripts/run_lep_scenario.py`**. Один вызов MCP на ВМ: **`lep_run_scenario`** (`scenario_name`, например `_template.json`).

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `MCP_HOST` | По умолчанию `0.0.0.0` |
| `MCP_PORT` | По умолчанию **`8765`**. Другой порт (например **`4040`**): перед запуском `set MCP_PORT=4040` / `$env:MCP_PORT="4040"`; в Cursor URL станет `http://<хост>:4040/mcp`. |
| `MCP_STATELESS_HTTP` | `1` / `true` — stateless-режим (масштабирование) |
| `MCP_REPO_ROOT` | Явный корень git для **`server_update`**. Обычно **не нужен** при **`git clone`** [map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker) (корень репо = папка сервера). См. [docs/GIT_SETUP.md](docs/GIT_SETUP.md). |
| `MCP_ALLOW_SELF_UPDATE` | **`1`** / **`true`** — разрешить **`server_update`**. Если переменная **не задана или пустая**, при старте **`src\server.py`** подставляется **`1`**. Отключить: **`0`**, **`false`**, **`no`**. Скрипт **`run_local.ps1`** без **`-NoSelfUpdate`** ведёт себя так же. |
| `MCP_RESTART_AFTER_UPDATE` | **`1`** / **`true`** (по умолчанию) — после успешного **`server_update`** запланировать автоперезапуск MCP. Helper [`scripts/mcp_restart_after_update.py`](scripts/mcp_restart_after_update.py): ждёт PID, **ждёт освобождения порта**, до **3** попыток `Popen`; логи — **`logs/mcp_restart_helper.log`**, stderr нового процесса — **`logs/mcp_server_stderr.log`**. Отключить: **`0`**, **`false`**, **`no`**. |
| `MCP_RESTART_LOG` | (Опционально) Полный путь к файлу журнала helper перезапуска; иначе **`logs/mcp_restart_helper.log`** под каталогом сервера. |
| `MCP_ALLOW_LAUNCH` | Выставляется **`server.py`** при старте: **`1`**, если не задан **`MCP_BLOCK_LAUNCH=1`**. Внешнее **`MCP_ALLOW_LAUNCH=0`** из планировщика больше не блокирует запуск. Запрет: **`MCP_BLOCK_LAUNCH=1`**. |
| `MCP_BLOCK_LAUNCH` | **`1`** / **`true`** — отключить **`launch_process`**. |
| `MCP_NANOCAD_EXE` | Полный путь к **`nCAD.exe`**, если **`AUTO_NANOCAD`** не находит установку (нестандартная папка). |
| `MCP_LEP_COMMAND` | Строка команды для вызова палитры LEP из командной строки nanoCAD (по умолчанию **`LEP`**). Используется инструментом **`nanocad_lep_prepare`**, если параметр **`lep_command`** не передан. |
| `MCP_LEP_OPEN_DWG` | (Опционально) Абсолютный путь к **`.dwg`**: подставляется в аргументы **первого** запуска **`nCAD.exe`** вместе с **`nanocad_lep_prepare`** / **`launch_process`**, чтобы автономно открыть эталонный чертёж (аналог **`LEP_GOLDEN_DWG`**). Если nCAD уже запущен и старт пропущен — см. `data.open_dwg_note` в журнале prepare. |
| `LEP_GOLDEN_DWG` | Поддерживается как **алиас** к пути DWG для **`nanocad_lep_prepare`** при холодном старте (если **`MCP_LEP_OPEN_DWG`** не задан). |
| `MCP_ACTION_JSONL` | Путь к файлу **JSONL** (одна строка = один JSON): успешные (`ok=true`) вызовы инструментов после фильтра. Пусто — логирование выключено. Каталог создаётся при первой записи. |
| `MCP_ACTION_JSONL_FILTER` | **`lep_only`** (по умолчанию) — только шаги, связанные с nanoCAD/LEP/модалками и т.п.; **`all`** — любой успешный инструмент. |
| `MCP_LEARN_JSONL` | Отдельный путь к **JSONL корпуса наблюдений** (`kind=cursor_interaction`, **`policy=none`**): параметры и краткий итог вызовов для **offline** / будущего распознавания. Пусто — канал выключен. Сервер **не читает** этот файл при UIA/capture и **не принимает** решений на его основе. |
| `MCP_LEARN_FILTER` | **`lep_only`** (по умолчанию) \| **`all`** — та же эвристика CAD/LEP, что у `MCP_ACTION_JSONL_FILTER`. |
| `MCP_LEARN_INCLUDE_FAILURES` | **`1`** / **`true`** — дописывать в корпус также вызовы с **`ok=false`** (краткий `message_excerpt`); иначе только успешные. |
| `MCP_CAPTURE_DIR` | Каталог для PNG, когда у **`capture_window`** / **`capture_monitor`** задан **`filename_suffix`**, но не задан **`out_path`**. Пусто — системный temp. |
| `MCP_MODAL_POLL_SEC` | Интервал опроса в **`uia_modal_ok`** / **`uia_modal_titlebar_close`** (секунды, по умолчанию **0.12**; было жёстко 0.25). Допустимый диапазон 0.03…2. |
| `MCP_SENDKEYS_MODAL_MAX_W` / `MCP_SENDKEYS_MODAL_MAX_H` | Макс. размер окна на переднем плане, чтобы **`send_keys`** считал его модалкой (**`#32770`** или **WinForms** в процессе **`nCAD.exe`**) и слал клавиши в него, а не в главное окно. По умолчанию 1400×950. |
| `MCP_UPDATE_USE_PS1` | На **Windows** при старте **`server.py`**, если переменная **не задана**, подставляется **`1`**: **`server_update`** вызывает PowerShell [scripts/update_server.ps1](scripts/update_server.ps1) (только **git pull** + **pip** в venv). Перезапуск процесса MCP остаётся в Python-коде `update.schedule_restart_after_update` (Windows: delayed `Start-Process`; non-Windows: helper). Отключить PS1-путь: **`0`** / **`false`** / **`no`**. |
| `MCP_AUTH_TOKEN` | (Опционально) если позже добавите reverse-proxy с проверкой Bearer — см. ниже. |
| `MCP_PYTHON` | Полный путь к `python.exe` для [scripts/setup_local.ps1](scripts/setup_local.ps1), если `python` не в PATH. |

## Автозапуск после обновления и «служба»

Классическая служба Windows под **LocalSystem** часто **не подходит** для UIA с nanoCAD на пользовательском столе. Рекомендации, логи перезапуска и скрипт планировщика при входе: **[docs/WINDOWS_AUTOSTART.md](docs/WINDOWS_AUTOSTART.md)** и **[scripts/Register-LepMcpLogonTask.ps1](scripts/Register-LepMcpLogonTask.ps1)**.

## Запуск

Из каталога `windows-mcp-server`:

```powershell
$env:MCP_HOST="0.0.0.0"
$env:MCP_PORT="8765"
$env:MCP_ALLOW_SELF_UPDATE="1"
$env:MCP_REPO_ROOT="D:\LEP"
.\.venv\Scripts\python.exe src\server.py
```

Либо `scripts\run_local.ps1` (подставит локальные `PIP_CACHE_DIR` / `TEMP` в каталоге проекта; по умолчанию включает **`MCP_ALLOW_SELF_UPDATE=1`**, чтобы из Cursor работал инструмент **`server_update`**). Для **`launch_process`**: **`run_local.ps1 -AllowLaunch`** (или задайте **`MCP_ALLOW_LAUNCH=1`**).

### Обновление сервера

1. **Код** — клонируй **[map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker)** на Windows; **`server_update`** с **`full`** делает **`git pull` + pip**. Подробно: **[docs/GIT_SETUP.md](docs/GIT_SETUP.md)**. Копирование папки без **`.git`** — только ручные обновления.
2. **Зависимости и git из агента:** при **`MCP_ALLOW_SELF_UPDATE=1`** вызовите инструмент **`server_update`**: `pip` (только pip), `git_pull` (pull + pip), `full` (то же, что `git_pull`). При **`MCP_RESTART_AFTER_UPDATE=1`** (по умолчанию) процесс MCP **перезапустится сам** через ~2 с после ответа; в **`data.restart_scheduled`** будет **`true`**. Иначе перезапустите **`server.py`** вручную после смены **`.py`**.
3. **Вручную на Windows:** `powershell -ExecutionPolicy Bypass -File scripts\update_server.ps1 -RepoRoot <корень LEP с .git>`.

Эндпоинт MCP по умолчанию: **`http://<host>:<port>/mcp`** (см. `streamable_http_path` в FastMCP).

## Cursor на Mac (удалённый MCP)

Агент в чате **не может** сам «подписаться» на ваш MCP: серверы задаются **в Cursor на вашем Mac** (файл настроек MCP / JSON в настройках). После сохранения конфига и перезапуска Cursor **тот же** агент в новых чатах сможет вызывать инструменты этого сервера, если Cursor их отдаёт в сессию.

1. **Cursor → Settings → MCP** (или правка JSON MCP вручную).
2. В корневой объект **`mcpServers`** добавьте блок из примера [cursor-mcp.example.json](cursor-mcp.example.json) (там зафиксирован актуальный **LAN**-эндпоинт `http://195.209.212.86:8765/mcp`; за прокси — HTTPS + Bearer) или [cursor-mcp.via-ssh-tunnel.example.json](cursor-mcp.via-ssh-tunnel.example.json) (локальный порт после туннеля).
3. Поле **`url`**: для прямого теста по сети — `http://<хост>:8765/mcp` (см. пример выше); в бою лучше **TLS + токен** на прокси.
4. **`headers`**: при reverse-proxy с Bearer — `Authorization: Bearer ...`; если прокси не проверяет токен, можно оставить пустой объект или убрать ключ по документации вашей версии Cursor.
5. Полный **перезапуск Cursor** после изменения конфига.

**SSH-туннель** (рекомендуется вместо голого IP в интернет): на Mac, пока сервер на Windows слушает `8765`:

```bash
ssh -N -L 18765:127.0.0.1:8765 user@<ваш-windows-хост>
```

В MCP укажите `http://127.0.0.1:18765/mcp` (порт `18765` можно заменить на свободный).

**Важно:** в разных версиях Cursor поведение удалённого MCP может отличаться; при сбоях см. [форум Cursor](https://forum.cursor.com) (темы про remote SSE/HTTP).

### Модалки LEP (WinForms и MessageBox)

- **`uia_modal_ok`**: кроме Win32 **`#32770`**, учитываются малые окна **`WindowsForms10.Window…`**, в т.ч. **owned** главным окном nanoCAD; поиск кнопки OK — прямой UIA, затем обход **`Button`**, затем **`{ENTER}`** (AcceptButton).
- **`send_keys`**: если на переднем плане маленькое WinForms-окно в процессе **`nCAD.exe`**, ввод уходит в него (**`data.via`: `foreground_winforms_modal`**), как для системной модалки **`#32770`**.
- После деплоя сравните **`agent_session` → `server.uia_tools_revision`** с ожидаемым значением в репозитории — так видно, что ВМ подтянула код.

### Корпус наблюдений (learn-only)

При заданном **`MCP_LEARN_JSONL`** после инструментов (тот же хук, что и для replay-лога) дописываются строки с **`policy: "none"`**: это **не** обучение в runtime и **не** влияние на клики. Данные предназначены для выгрузки и последующей обработки вне сервера. Инструмент **`learn_log_recent`** — только просмотр хвоста файла. В записи **нет** `png_base64`.

### Интеграция с product-delivery (полный цикл в репозитории LEP)

Сервер даёт **полный набор** для автоматизированного тестирования плагина LEP в nanoCAD, включая **`lep_run_scenario`** (один MCP-вызов = весь JSON-сценарий на ВМ без Cursor) и **`nanocad_lep_prepare`** с опциональным **`open_dwg_path`** / **`MCP_LEP_OPEN_DWG`**, дерево **`uia_list_subtree`** от якоря палитры, **`uia_click`** / **`send_keys`**, закрытие модалок (**`uia_modal_ok`**, **`uia_modal_titlebar_close`**), координатные **`mouse_*`**, пары **`capture_window`** + **`capture_monitor`** (в т.ч. `include_base64=true`), **`launch_process`** / **`AUTO_NANOCAD`**, лог шагов **`action_json_log_recent`**, JSON-сценарии **`scenarios/`** + **`scripts/run_lep_scenario.py`**, матрица **`scripts/run_lep_qa_matrix.py`**.

В Cursor skill **product-delivery** (`.cursor/skills/product-delivery/SKILL.md`) после этапа разработки может вызываться субагент **`lep-plugin-tester`**, который обязан следовать workflow из **`agent_session`** и правилам **`.cursor/agents/lep-plugin-tester.md`**. Деплой на ВМ и проверка версии UIA-модуля на сервере: **`docs/DEPLOY_VM_CHECKLIST.md`**. Если ревизия **`server.uia_tools_revision`** в **`agent_session`** не совпадает с ожидаемой после merge, а на ВМ включён **`MCP_ALLOW_SELF_UPDATE`** и задан **`MCP_REPO_ROOT`** с **`.git`** — инструмент **`server_update`** (`git_pull` / `full`) подтягивает код и при **`MCP_RESTART_AFTER_UPDATE=1`** перезапускает процесс MCP; затем снова **`health`** → **`agent_session`** и повтор приёмочного прогона nanoCAD (см. пункт **2g** в **`agent_session` → `workflow`**).

## Контракт ответов и коммуникация агента

Каждый инструмент возвращает **одну строку — валидный JSON** с полями:

| Поле | Смысл |
|------|--------|
| `ok` | `true` / `false` |
| `code` | `OK` или код ошибки (`ERR_PLATFORM`, `ERR_VALIDATION`, `ERR_NOT_FOUND`, `ERR_TIMEOUT`, `ERR_UIA`, `ERR_UPDATE`, `ERR_FORBIDDEN`, …) |
| `message` | Кратко для человека |
| `protocol_version` | Версия контракта (см. `src/protocol.py`; **1.7** — `uia_list_subtree`, `mouse_click_window`, расширенный Win32-фолбэк `uia_modal_ok`, фокус в `send_keys`) |
| `request_id` | UUID; совпадает с переданным **`client_request_id`**, если агент его задал |
| `server_time_utc` | Метка времени ответа |
| `data` | Полезная нагрузка (объект; при ошибке может быть пустым или с диагностикой) |

**Рекомендуемый порядок вызовов для агента**

1. **`health`** — проверить связь и то, что ответ парсится.
2. **`agent_session`** — получить `protocol_version`, список инструментов, **`workflow`**, поле **`lep_ui_titles_hint`** (подсказки `title_contains` для LEP), снимок безопасных env.
2a. **С нуля (ВМ / чистый сеанс):** один вызов **`nanocad_lep_prepare`** — запуск **`nCAD.exe`** (если ещё не в UIA), закрытие типовых модалок, команда LEP, ожидание **`lep_palette_root`**; в **`data.steps`** — журнал шагов. Затем пара **`capture_*`** для визуальной проверки.
2f. **Полностью автономно (без пошагового агента):** один вызов **`lep_run_scenario(scenario_name)`** — весь сценарий из **`scenarios/`** выполняется на сервере; альтернатива — **`scripts/execute_lep_scenario_local.py`** в пользовательской сессии ВМ. Для эталонного чертежа при первом запуске nCAD см. **`open_dwg_path`** / **`MCP_LEP_OPEN_DWG`** / **`LEP_GOLDEN_DWG`** в **`nanocad_lep_prepare`** (или первый шаг сценария с тем же вызовом).
3. **`uia_list_subtree`** (LEP) — карта UI **только палитры** (якорь `lep_palette_root` или regex по заголовку); меньше `truncated`, видны подвкладки **Создание / Анализ / …**. Иначе **`uia_list`** по `nCAD.exe` с большим `max_nodes` — смотреть `data.truncated`.
4. При необходимости **`wait_for_element`**, затем **`uia_click`**; при `ERR_NOT_FOUND` снова **`uia_list`**.
4b. Если на **`capture_*`** видна **MessageBox** / **«Внимание»**, а **`uia_click`** по **OK** в **`nCAD.exe`** даёт **`ERR_NOT_FOUND`** — **`uia_modal_ok`**, при необходимости **`uia_modal_titlebar_close`** (крестик), иначе сначала **`mouse_move_smooth`** (или **`mouse_move`**) к точке, затем **`mouse_click`** по координатам крестика/OK (расчёт от снимка / границ окна) — иначе курсор «прыгает» и на RDP не видно движения; затем снова пару снимков.
5. Один и тот же **`client_request_id`** — во все инструменты одной задачи.
6. **После каждого `send_keys` / `uia_click` / шага, меняющего экран:** **`capture_window`** и **`capture_monitor`** с **`include_base64=true`** — по **обоим** снимкам **подтвердить**, что **результат шага достигнут** (нужная вкладка/панель, нет лишней модалки, при необходимости виден кадр чертежа). Успех **`uia_click`** (`ok: true`) не равен успеху сценария. При расхождении с ожиданием — не PASS и не следующий шаг.
7. **После проверки скринов:** снова **`uia_list`**; для плагина LEP — дополнительно вызовы с **`title_contains`** из `lep_ui_titles_hint`, при **`truncated`** увеличить **`max_depth` / `max_nodes`** и повторить, пока дерево плагина не описано достаточно полно.
8. Не игнорировать модальные окна (**«Совет дня»**, ошибки **NETLOAD** и т.д.); снимок должен это показывать.
9. Если после команд плагина в UI нет ожидаемых элементов — сообщить пользователю (загрузка DLL, `LEP.cfg`), не имитировать успех.

## Инструменты

| Инструмент | Назначение |
|------------|------------|
| `health` | Пинг: `ok=true`, `data.status=alive` |
| `agent_session` | Снимок для агента: workflow, контракт, env, список инструментов |
| `server_info` | Версия Python, пути, git — в `data` |
| `server_update` | `pip` / `git_pull` / `full`; лог в `data.log`; при успехе **`data.restart_scheduled`** — запланирован автоперезапуск (если не **`MCP_RESTART_AFTER_UPDATE=0`**). Нужен **`MCP_ALLOW_SELF_UPDATE=1`**; иначе `ERR_FORBIDDEN`. |
| `uia_list` | Плоский список элементов в `data.items`; `process_name` (exe) или `title_contains` |
| `uia_list_subtree` | Как `uia_list`, но обход **от якоря палитры LEP** (`anchor_automation_id`, по умолчанию `lep_palette_root`, иначе regex по имени) — не съедает квоту лентой |
| `uia_click` | Клик по `automation_id` / `name` / `control_type`, опционально `nth` |
| `uia_modal_ok` | Закрыть модалку **MessageBox** / `#32770`: UIA + Win32 (owned от `owner_process_name`, дочерние **Button**, `GetDlgItem(1)`); в `data` — `via`, `hwnd`, `owner_hwnd` |
| `uia_modal_titlebar_close` | Закрыть ту же модалку **кликом по [X]** в caption: координаты от `rectangle()` окна и **DPI** (`GetDpiForWindow`) |
| `mouse_move` | Переместить курсор в **экранные** координаты **без клика** (чтобы было видно на удалённом столе) |
| `mouse_move_smooth` | Плавно вести курсор от **текущей** позиции к `(screen_x, screen_y)`: параметры `steps`, `pause_ms` — перед **`mouse_click`** для наглядности |
| `mouse_click` | Клик мыши в **экранных** координатах `screen_x`, `screen_y` (`left`/`right`/`middle`, опционально `double`) — вручную по скрину |
| `mouse_click_window` | Клик в **клиентских** координатах выбранного окна (`process_name` / `title_contains`): перевод в экран через **ClientToScreen** — предпочтительнее при расхождении DPI с bbox |
| `wait_for_element` | Ожидание появления элемента; таймаут → `ERR_TIMEOUT` |
| `send_keys` | Ввод текста в окно (осторожно) |
| `capture_window` | PNG окна: `data.path` на сервере; **`data.png_base64`** (+ MIME в `data.image_mime_type`) для клиента на Mac. **`filename_suffix`**: если **`out_path`** не задан — имя файла содержит слаг (латиница); иначе из заголовка окна (`data.filename_slug_used`). Каталог: **`MCP_CAPTURE_DIR`** или temp. `max_edge_px` уменьшает встроенное изображение при больших мониторах; файл на диске остаётся полным кадром. В `data.content_hint` — эвристика «кадр пустой/без видео». **`data.bbox`** — **экранные** пиксели кадра. |
| `capture_monitor` | PNG **целого монитора** (MSS): `monitor_index` **0** / **1** и т.д. Параметр **`filename_suffix`** — как у **`capture_window`**, если **`out_path`** не задан. Те же `include_base64` / `max_edge_px` / `content_hint`. |
| `launch_process` | Запуск `.exe` на Windows (отдельный процесс). Нужен **`MCP_ALLOW_LAUNCH=1`**; иначе `ERR_FORBIDDEN`. **`executable`**: полный путь или **`AUTO_NANOCAD`** / **`AUTO`** — поиск `nCAD.exe` в PATH и типичных каталогах Nanosoft. После старта ждёт появления процесса в UIA (`wait_timeout_sec`). |
| `nanocad_lep_prepare` | Сценарий «nanoCAD + палитра LEP»: проверка UIA **`nCAD.exe`** → при необходимости **`launch_process` (AUTO_NANOCAD)** (с опциональным путём **`.dwg`** из **`open_dwg_path`** / **`MCP_LEP_OPEN_DWG`** / **`LEP_GOLDEN_DWG`**) → серия **`uia_modal_ok`** / **`uia_modal_titlebar_close`** → клик командной строки (**`1011`**) → **`send_keys`** (команда из **`lep_command`** / **`MCP_LEP_COMMAND`** / **`LEP`**) → **`wait_for_element`** на **`lep_palette_root`**. Реализация: **`src/nanocad_bootstrap.py`**. При уже открытой палитре повторный ввод команды не выполняется (`data.skipped_command_input`). |
| `lep_run_scenario` | Выполнить **`scenarios/<имя>.json`** на сервере: шаги **`invoke`** по порядку через те же функции, что и отдельные MCP-инструменты; **`data.step_log`**. Опционально **`stop_on_first_error`** переопределяет поле в JSON. Автономный прогон без Cursor. Только Windows; имена файлов без `..`. |
| `lep_run_scenario_sequence` | Несколько сценариев подряд **одним вызовом**: аргумент **`scenario_names_csv`** (имена через запятую); по умолчанию **`lep_mcp_full_operability_smoke.json,lep_plugin_full_palette_uia.json`**. Ответ: **`data.runs`**, **`data.all_scenarios_ok`**. Максимум **8** файлов за вызов. |
| `action_json_log_recent` | Чтение **последних** записей из **`MCP_ACTION_JSONL`** (`data.entries`: `action_signature`, `replay_hint`, `params`, `response_summary`). Если лог не настроен — `data.enabled=false`. Используйте для пропуска уже выполненных шагов в повторном прогоне. |
| `learn_log_recent` | Чтение **последних** записей из **`MCP_LEARN_JSONL`** (`policy=none`, без влияния на инструменты). Если корпус выключен — `data.enabled=false`. |

**Формат строки лога** (append, UTF-8): `logged_at_utc`, `tool`, `request_id`, **`action_signature`** (SHA-256 от tool+params, 24 hex — стабильный ключ шага), **`replay_hint`**, `params` (без секретов; длинные строки усечены), `response_summary`, `protocol_version`.

**Сценарии QA (JSON):** каталог [scenarios/](scenarios/README.md); генерация промпта для агента: `python scripts/run_lep_scenario.py --scenario scenarios/_template.json` (или `--name _template`).

Обновление вручную без MCP: [scripts/update_server.ps1](scripts/update_server.ps1).

## Безопасность

- Не выставляйте порт в интернет без **TLS** (обратный прокси: Caddy, nginx) и **ограничения по IP**/VPN.
- **`server_update`** по умолчанию **включён**, если не задать **`MCP_ALLOW_SELF_UPDATE=0`** (или `false` / `no`). На недоверенных хостах отключайте явно.
- Логи не должны содержать содержимое чертежей/персональные данные.

## Копирование с Mac на рабочий стол Windows (ВМ)

С агента **нельзя** положить файлы на ВМ без сетевого доступа (SSH и т.д.). Скрипт:

- [scripts/deploy_to_windows_desktop.sh](scripts/deploy_to_windows_desktop.sh) — **`rsync`** по SSH в каталог вроде **`C:/Users/Admin/Desktop/windows-mcp-server`** (исключает `.venv`, `.git`).

Пример на Mac:

```bash
cd /path/to/LEP/windows-mcp-server
export WINDOWS_SSH="Admin@192.168.x.x"
export REMOTE_DESKTOP_DIR="C:/Users/Admin/Desktop/windows-mcp-server"
./scripts/deploy_to_windows_desktop.sh
```

На Windows должен быть **OpenSSH Server**, пользователь с правом на каталог, ключ или пароль для `ssh`. После копирования — **перезапуск MCP**.

## Развёртывание и RDS

- При отключении RDP сессия может блокироваться — уточните политику **сохранения сессии**.
- **Чёрный снимок** (`capture_window` / **`capture_monitor`**) после выхода из RDP — это не баг MCP: Windows часто **не отдаёт растровый рабочий стол** без активного вывода. Инструменты лишь читают буфер; «оживить» его можно так:
  - **Виртуальный монитор**: HDMI-заглушка на видеовыходе или софт вроде **usbmmidd** (виртуальный дисплей) / драйвер виртуального монитора — тогда сессия остаётся с ненулевым framebuffer.
  - Не завершать сессию при отключении RDP; при необходимости оставлять **локальный вход** на консоли под тем же пользователем.
  - Для проверки с Mac вызывайте **`capture_monitor`** с `monitor_index=1` и смотрите **`data.content_hint`**: `likely_blank_or_no_video_output` означает «кадр почти однотонный» — имеет смысл включить виртуальный дисплей и повторить.
- Автозапуск: **Планировщик заданий** «При входе пользователя» с запуском `pythonw`/`python` и рабочей папкой `windows-mcp-server`, либо скрипт в автозагрузке профиля.

## Ограничения

- Селекторы UI ломаются при смене версии плагина — закладывайте регрессию через `uia_list` + сохранённые эталоны.
- Координатные клики «в лоб» в протокол не выносились; при необходимости добавьте отдельный инструмент с env-флагом `MCP_DANGER_*` (см. план LEP).

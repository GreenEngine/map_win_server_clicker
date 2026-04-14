# LEP Windows MCP Server

Репозиторий на GitHub: **[GreenEngine/map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker)**.

MCP-сервер для **Windows Server / Windows 10+**: **Streamable HTTP**, инструменты **UI Automation** (pywinauto) для NanoCAD/плагина и других оконных приложений, плюс **`server_update`** — обновление кода/зависимостей на сервере по запросу агента (с флагом безопасности).

## Требования

- Windows, Python **3.10+**
- Запуск в **интерактивной пользовательской сессии** (тот же пользователь, под которым открыт NanoCAD / RDP-сеанс). Служба без стола обычно **не** подходит для UIA.
- Права на установку пакетов в выбранный venv.

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

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `MCP_HOST` | По умолчанию `0.0.0.0` |
| `MCP_PORT` | По умолчанию **`8765`**. Другой порт (например **`4040`**): перед запуском `set MCP_PORT=4040` / `$env:MCP_PORT="4040"`; в Cursor URL станет `http://<хост>:4040/mcp`. |
| `MCP_STATELESS_HTTP` | `1` / `true` — stateless-режим (масштабирование) |
| `MCP_REPO_ROOT` | Явный корень git для **`server_update`**. Обычно **не нужен**: репозиторий git заведён **внутри папки `windows-mcp-server`** (см. [docs/GIT_SETUP.md](docs/GIT_SETUP.md)). Задавайте только если **`.git`** лежит **выше** (монорепо). |
| `MCP_ALLOW_SELF_UPDATE` | **`1`** / **`true`** — разрешить **`server_update`**. Если переменная **не задана или пустая**, при старте **`src\server.py`** подставляется **`1`**. Отключить: **`0`**, **`false`**, **`no`**. Скрипт **`run_local.ps1`** без **`-NoSelfUpdate`** ведёт себя так же. |
| `MCP_ALLOW_LAUNCH` | Выставляется **`server.py`** при старте: **`1`**, если не задан **`MCP_BLOCK_LAUNCH=1`**. Внешнее **`MCP_ALLOW_LAUNCH=0`** из планировщика больше не блокирует запуск. Запрет: **`MCP_BLOCK_LAUNCH=1`**. |
| `MCP_BLOCK_LAUNCH` | **`1`** / **`true`** — отключить **`launch_process`**. |
| `MCP_NANOCAD_EXE` | Полный путь к **`nCAD.exe`**, если **`AUTO_NANOCAD`** не находит установку (нестандартная папка). |
| `MCP_UPDATE_USE_PS1` | **`1`** — на Windows выполнять [scripts/update_server.ps1](scripts/update_server.ps1) вместо встроенного Python-пути (удобно для единой политики обновлений). |
| `MCP_AUTH_TOKEN` | (Опционально) если позже добавите reverse-proxy с проверкой Bearer — см. ниже. |
| `MCP_PYTHON` | Полный путь к `python.exe` для [scripts/setup_local.ps1](scripts/setup_local.ps1), если `python` не в PATH. |

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

1. **Код** — в каталоге сервера. Рекомендуется отдельный git-репозиторий **только для `windows-mcp-server`**: **`git clone …\windows-mcp-server`**, затем **`server_update`** `full` тянет коммиты. Подробно: **[docs/GIT_SETUP.md](docs/GIT_SETUP.md)**. Альтернатива — копирование папки с Mac без git (тогда обновления только вручную).
2. **Зависимости и git из агента:** при **`MCP_ALLOW_SELF_UPDATE=1`** вызовите инструмент **`server_update`**: `pip` (только pip), `git_pull` (pull + pip), `full` (то же, что `git_pull`). После смены **`.py` обязательно перезапустите** процесс `server.py`.
3. **Вручную на Windows:** `powershell -ExecutionPolicy Bypass -File scripts\update_server.ps1 -RepoRoot <корень LEP с .git>`.

Эндпоинт MCP по умолчанию: **`http://<host>:<port>/mcp`** (см. `streamable_http_path` в FastMCP).

## Cursor на Mac (удалённый MCP)

Агент в чате **не может** сам «подписаться» на ваш MCP: серверы задаются **в Cursor на вашем Mac** (файл настроек MCP / JSON в настройках). После сохранения конфига и перезапуска Cursor **тот же** агент в новых чатах сможет вызывать инструменты этого сервера, если Cursor их отдаёт в сессию.

1. **Cursor → Settings → MCP** (или правка JSON MCP вручную).
2. В корневой объект **`mcpServers`** добавьте блок из примера [cursor-mcp.example.json](cursor-mcp.example.json) (HTTPS + Bearer за прокси) или [cursor-mcp.via-ssh-tunnel.example.json](cursor-mcp.via-ssh-tunnel.example.json) (локальный порт после туннеля).
3. Поле **`url`**: для прямого теста по сети — `http://<хост>:8765/mcp`; в бою лучше **TLS + токен** на прокси.
4. **`headers`**: при reverse-proxy с Bearer — `Authorization: Bearer ...`; если прокси не проверяет токен, можно оставить пустой объект или убрать ключ по документации вашей версии Cursor.
5. Полный **перезапуск Cursor** после изменения конфига.

**SSH-туннель** (рекомендуется вместо голого IP в интернет): на Mac, пока сервер на Windows слушает `8765`:

```bash
ssh -N -L 18765:127.0.0.1:8765 user@<ваш-windows-хост>
```

В MCP укажите `http://127.0.0.1:18765/mcp` (порт `18765` можно заменить на свободный).

**Важно:** в разных версиях Cursor поведение удалённого MCP может отличаться; при сбоях см. [форум Cursor](https://forum.cursor.com) (темы про remote SSE/HTTP).

## Контракт ответов и коммуникация агента

Каждый инструмент возвращает **одну строку — валидный JSON** с полями:

| Поле | Смысл |
|------|--------|
| `ok` | `true` / `false` |
| `code` | `OK` или код ошибки (`ERR_PLATFORM`, `ERR_VALIDATION`, `ERR_NOT_FOUND`, `ERR_TIMEOUT`, `ERR_UIA`, `ERR_UPDATE`, `ERR_FORBIDDEN`, …) |
| `message` | Кратко для человека |
| `protocol_version` | Версия контракта (см. `src/protocol.py`; **1.5** — `launch_process`, `capture_monitor`, `content_hint`) |
| `request_id` | UUID; совпадает с переданным **`client_request_id`**, если агент его задал |
| `server_time_utc` | Метка времени ответа |
| `data` | Полезная нагрузка (объект; при ошибке может быть пустым или с диагностикой) |

**Рекомендуемый порядок вызовов для агента**

1. **`health`** — проверить связь и то, что ответ парсится.
2. **`agent_session`** — получить `protocol_version`, список инструментов, **`workflow`**, поле **`lep_ui_titles_hint`** (подсказки `title_contains` для LEP), снимок безопасных env.
3. **`uia_list`** — построить карту UI; смотреть `data.truncated` (лимиты глубины/узлов).
4. При необходимости **`wait_for_element`**, затем **`uia_click`**; при `ERR_NOT_FOUND` снова **`uia_list`**.
5. Один и тот же **`client_request_id`** — во все инструменты одной задачи.
6. **После каждого `send_keys` / `uia_click` / шага, меняющего экран:** сразу **`capture_window`** целевого окна с **`include_base64=true`** — агент **сам** смотрит **`data.png_base64`** и сверяет с ожидаемым результатом (не продолжать вслепую при расхождении).
7. **После каждого снимка:** снова **`uia_list`**; для плагина LEP — дополнительно вызовы с **`title_contains`** из `lep_ui_titles_hint`, при **`truncated`** увеличить **`max_depth` / `max_nodes`** и повторить, пока дерево плагина не описано достаточно полно.
8. Не игнорировать модальные окна (**«Совет дня»**, ошибки **NETLOAD** и т.д.); снимок должен это показывать.
9. Если после команд плагина в UI нет ожидаемых элементов — сообщить пользователю (загрузка DLL, `LEP.cfg`), не имитировать успех.

## Инструменты

| Инструмент | Назначение |
|------------|------------|
| `health` | Пинг: `ok=true`, `data.status=alive` |
| `agent_session` | Снимок для агента: workflow, контракт, env, список инструментов |
| `server_info` | Версия Python, пути, git — в `data` |
| `server_update` | `pip` / `git_pull` / `full`; лог в `data.log`. Нужен **`MCP_ALLOW_SELF_UPDATE=1`**; иначе `ERR_FORBIDDEN`. После обновления `.py` **перезапустите** процесс сервера. |
| `uia_list` | Плоский список элементов в `data.items`; `process_name` (exe) или `title_contains` |
| `uia_click` | Клик по `automation_id` / `name` / `control_type`, опционально `nth` |
| `wait_for_element` | Ожидание появления элемента; таймаут → `ERR_TIMEOUT` |
| `send_keys` | Ввод текста в окно (осторожно) |
| `capture_window` | PNG окна: `data.path` на сервере; **`data.png_base64`** (+ MIME в `data.image_mime_type`) для клиента на Mac. `max_edge_px` уменьшает встроенное изображение при больших мониторах; файл на диске остаётся полным кадром. В `data.content_hint` — эвристика «кадр пустой/без видео». |
| `capture_monitor` | PNG **целого монитора** (библиотека MSS): `monitor_index` **0** — все мониторы одним снимком, **1** — основной (по умолчанию). Полезно, когда нужен рабочий стол без привязки к `nCAD.exe`. Те же `include_base64` / `max_edge_px` / `content_hint`. |
| `launch_process` | Запуск `.exe` на Windows (отдельный процесс). Нужен **`MCP_ALLOW_LAUNCH=1`**; иначе `ERR_FORBIDDEN`. **`executable`**: полный путь или **`AUTO_NANOCAD`** / **`AUTO`** — поиск `nCAD.exe` в PATH и типичных каталогах Nanosoft. После старта ждёт появления процесса в UIA (`wait_timeout_sec`). |

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

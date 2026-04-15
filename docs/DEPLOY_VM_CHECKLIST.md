# Чеклист: выкатить актуальный `windows-mcp-server` на ВМ

Цель: на удалённой Windows после merge в монорепо LEP агент видит **`protocol_version` 1.7+**, инструменты **`uia_list_subtree`**, **`mouse_click_window`**, **`mouse_move`**, **`mouse_move_smooth`**, обновлённый **`uia_modal_ok`** / **`send_keys`**.

**URL MCP для клиента в сети (Cursor на Mac и т.п.):** `http://195.209.212.86:8765/mcp` — см. [cursor-mcp.example.json](../cursor-mcp.example.json). За прокси с TLS и Bearer подставьте свой хост и заголовок.

## 1. Доставить код на ВМ

Один из вариантов:

- **rsync / копирование** из Mac: [scripts/deploy_to_windows_desktop.sh](../scripts/deploy_to_windows_desktop.sh) (см. README).
- **git pull** в каталоге, где клонирован репозиторий с этой папкой (или отдельный [map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker) — синхронизируйте с LEP вручную).

## 2. Перезапуск MCP

- После **merge в монорепо LEP** на Mac: на ВМ через Cursor / агент вызвать **`server_update`** с режимом **`git_pull`** или **`full`** при **`MCP_ALLOW_SELF_UPDATE=1`** (по умолчанию в `server.py`). Дождаться **`data.restart_scheduled`: true** (или вручную перезапустить `server.py` через ~2 с) — иначе агент продолжит работать со **старой** копией `uia_tools.py` (расхождение `uia_tools_revision` в **`agent_session`**).
- Либо вручную на ВМ: остановить процесс `python … src\server.py`, снова запустить из venv (см. [README.md](../README.md)).

## 3. Проверка после деплоя

Вызвать **`agent_session`** и убедиться:

- в **`protocol_version`** ожидаемая строка (см. `src/protocol.py`);
- в **`server`** присутствуют **`uia_tools_revision`** и **`uia_modal_title_pattern_sha12`** (сверка с актуальным репо после выкладки);
- в списке **`tools`** есть **`uia_list_subtree`**, **`mouse_click_window`**, **`mouse_move`**, **`mouse_move_smooth`**, **`lep_run_scenario`**.

Затем короткий **`health`**.

**Автономный прогон без Cursor (один вызов MCP):** после деплоя задайте при необходимости **`MCP_LEP_OPEN_DWG`** или **`LEP_GOLDEN_DWG`** (эталонный **`.dwg`** только при **холодном** старте через **`launch_process`** внутри **`nanocad_lep_prepare`** — см. `data.open_dwg_note` в ответе, если nCAD уже был запущен). Вызовите **`lep_run_scenario`** с **`scenario_name`**, например **`_template.json`** — в **`data.step_log`** виден журнал шагов; при ошибке смотрите последний элемент лога.

Smoke WinForms (опционально): палитра LEP → **Генератор чертежей** → «Профили пересечений (лист A3)» → **Сгенерировать** → на диалоге **«Профили пересечений»** вызвать **`uia_modal_ok`** (или **`send_keys`** с `{ENTER}` на переднем плане) — диалог должен закрыться без подбора координат.

### Корпус наблюдений (опционально)

- Задать **`MCP_LEARN_JSONL`** (например рядом с `windows-mcp-server\.tmp\learn_corpus.jsonl`) — при работе агента из Cursor будут накапливаться записи **`observe_only`** для offline-анализа. Периодически копируйте файл с ВМ, ротируйте по размеру.
- **`learn_log_recent`** — проверка, что строки пишутся. На поведение UIA это **не** влияет.

Актуально для QA LEP (после merge в монорепо):

- В **`uia_tools.py`** расширен встроенный **`title_regex`** у **`uia_modal_ok`** / **`uia_modal_titlebar_close`**: добавлены заголовки **`Профили пересечений`** и **`Построение трассы`**, чтобы закрывать диалог параметров листа пересечений и итоговые `MessageBox` после генератора без явного `title_regex` в вызове.

## 4. Плагин LEP

Чтобы **`uia_list_subtree`** находил якорь по **`lep_palette_root`**, на ВМ должна быть сборка плагина с обновлённым **`MainForm`** (поле **`Name`** у **`_innerPanel`**). Иначе сервер всё равно отработает через **fallback regex** по заголовку окна.

Для сценариев **«Генератор чертежей»** / **`lep-plugin-tester`**: в сборке должен быть **`CheckedListBox`** типов DWG с **`AutomationId`** **`lep_clb_drawing_types`** (`DrawingGeneratorControl`), см. **`ALL/docs/QA_UiaIds.md`** — фокус по **`uia_click`** на списке и клавиши **`{HOME}{DOWN 6}{SPACE}`** для пункта «Профили пересечений (лист A3)».

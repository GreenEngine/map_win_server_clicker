# Чеклист: выкатить актуальный `windows-mcp-server` на ВМ

Цель: на удалённой Windows после merge в монорепо LEP агент видит **`protocol_version` 1.7+**, инструменты **`uia_list_subtree`**, **`mouse_click_window`**, **`mouse_move`**, **`mouse_move_smooth`**, обновлённый **`uia_modal_ok`** / **`send_keys`**.

## 1. Доставить код на ВМ

Один из вариантов:

- **rsync / копирование** из Mac: [scripts/deploy_to_windows_desktop.sh](../scripts/deploy_to_windows_desktop.sh) (см. README).
- **git pull** в каталоге, где клонирован репозиторий с этой папкой (или отдельный [map_win_server_clicker](https://github.com/GreenEngine/map_win_server_clicker) — синхронизируйте с LEP вручную).

## 2. Перезапуск MCP

- Через Cursor / агент: инструмент **`server_update`** с режимом **`git_pull`** или **`full`** при **`MCP_ALLOW_SELF_UPDATE=1`** (по умолчанию в `server.py`).
- Либо вручную на ВМ: остановить процесс `python … src\server.py`, снова запустить из venv (см. [README.md](../README.md)).

## 3. Проверка после деплоя

Вызвать **`agent_session`** и убедиться:

- в **`protocol_version`** ожидаемая строка (см. `src/protocol.py`);
- в списке **`tools`** есть **`uia_list_subtree`**, **`mouse_click_window`**, **`mouse_move`**, **`mouse_move_smooth`**.

Затем короткий **`health`**.

## 4. Плагин LEP

Чтобы **`uia_list_subtree`** находил якорь по **`lep_palette_root`**, на ВМ должна быть сборка плагина с обновлённым **`MainForm`** (поле **`Name`** у **`_innerPanel`**). Иначе сервер всё равно отработает через **fallback regex** по заголовку окна.

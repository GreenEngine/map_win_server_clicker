"""Снимок состояния сервера для агента: возможности, шаги коммуникации, безопасные env-флаги."""

from __future__ import annotations

import os
import sys
from typing import Any

from src import uia_tools
from src import update as update_mod
from src.protocol import PROTOCOL_VERSION


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _safe_env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return None
    if "TOKEN" in name.upper() or "SECRET" in name.upper() or "PASSWORD" in name.upper():
        return "***" if v else None
    return v


def agent_session_payload() -> dict[str, Any]:
    ver = update_mod.server_version_dict()
    ver.update(uia_tools.uia_revision_payload())
    tools = [
        {"name": "health", "role": "проверка живости; всегда вызывать первым при сомнениях в сети"},
        {"name": "agent_session", "role": "этот снимок: версия протокола, шаги, env"},
        {
            "name": "lep_qa_catalog",
            "role": "список scenarios/*.json, пути к матрице QA, порядок инструментов для полного теста LEP; вызывать после agent_session перед длинным сценарием",
        },
        {"name": "server_info", "role": "краткая версия/git/python"},
        {"name": "server_update", "role": "обновление pip/git; только при MCP_ALLOW_SELF_UPDATE=1"},
        {"name": "uia_list", "role": "дерево UI в JSON (data.items); смотреть data.truncated"},
        {
            "name": "uia_list_subtree",
            "role": "LEP: дерево только под якорем палитры (anchor_automation_id lep_palette_root или regex); меньше truncated, видны подвкладки Трасса",
        },
        {
            "name": "uia_click",
            "role": "клик по селектору; сразу после — capture_window + capture_monitor (base64), проверка результата по скринам, затем uia_list_subtree или uia_list (см. workflow)",
        },
        {
            "name": "uia_modal_ok",
            "role": "закрыть MessageBox / WinForms-модалку LEP (OK/ОК): UIA child + обход Button + Accept {ENTER}; Win32 #32770; приоритет owned nCAD; data.via / hwnd для отчёта",
        },
        {
            "name": "uia_modal_titlebar_close",
            "role": "закрыть модалку кликом по [X] в заголовке (координаты от окна + DPI); если не сработало — mouse_click по координатам со скрина",
        },
        {
            "name": "mouse_click",
            "role": "клик мыши в экранных координатах (screen_x, screen_y) — крестик/точка, вычисленная агентом по capture_monitor/window",
        },
        {
            "name": "mouse_click_window",
            "role": "клик в клиентских координатах окна (ClientToScreen) — надёжнее DPI, чем screen_x/y от bbox скрина",
        },
        {
            "name": "mouse_move",
            "role": "переместить курсор без клика (мгновенно) — чтобы было видно на RDP перед действием",
        },
        {
            "name": "mouse_move_smooth",
            "role": "плавно вести курсор к (screen_x, screen_y) от текущей позиции (steps, pause_ms) — перед mouse_click для наглядности",
        },
        {"name": "wait_for_element", "role": "ожидание элемента; ERR_TIMEOUT если не дождались"},
        {
            "name": "send_keys",
            "role": "ввод текста: передний план — модалка #32770 или малое WinForms окна nCAD.exe (см. via); иначе process_name/title_contains + SetForegroundWindow; затем capture_* и uia_list",
        },
        {
            "name": "capture_window",
            "role": "Снимок окна: data.png_base64 (include_base64=true) — пара с capture_monitor; по картинке подтвердить эффект шага",
        },
        {
            "name": "capture_monitor",
            "role": "Снимок целого монитора (MSS); при отключённом RDP без виртуального дисплея смотреть data.content_hint",
        },
        {
            "name": "launch_process",
            "role": "Запуск .exe; отключить: MCP_BLOCK_LAUNCH=1. executable=AUTO_NANOCAD — поиск nCAD.exe",
        },
        {
            "name": "nanocad_lep_prepare",
            "role": "Один вызов: nCAD в UIA → launch при необходимости → модалки → командная строка 1011 → LEP (MCP_LEP_COMMAND) → wait lep_palette_root; data.steps; open_dwg_path / MCP_LEP_OPEN_DWG / LEP_GOLDEN_DWG — аргумент запуска nCAD для эталонного DWG",
        },
        {
            "name": "lep_run_scenario",
            "role": "выполнить scenarios/<имя>.json на сервере без Cursor: шаги invoke из JSON по порядку; автономный прогон; только Windows и безопасные имена файлов",
        },
        {
            "name": "action_json_log_recent",
            "role": "Хвост JSONL-лога успешных шагов (MCP_ACTION_JSONL): entries[].action_signature / replay_hint — чтобы не дублировать сценарий",
        },
        {
            "name": "learn_log_recent",
            "role": "Хвост JSONL корпуса наблюдений (MCP_LEARN_JSONL): policy=none — сервер не использует эти данные при кликах; только offline / будущее распознавание",
        },
    ]
    workflow = [
        "1) Вызвать health — убедиться, что JSON парсится и ok=true.",
        "2) Вызвать agent_session — прочитать protocol_version, server.uia_tools_revision / uia_modal_title_pattern_sha12 (сверка с репо после деплоя) и рекомендуемые инструменты.",
        "2b) Для полного плана прогона LEP вызвать lep_qa_catalog — список JSON-сценариев, подсказки CLI (run_lep_scenario / run_lep_qa_matrix), порядок smoke-инструментов.",
        "2a) С нуля или после перезагрузки ВМ: nanocad_lep_prepare (journal в data.steps) — затем capture_window + capture_monitor для визуальной проверки палитры.",
        "2c) Если на сервере задан MCP_ACTION_JSONL — при успешных шагах (фильтр lep_only по умолчанию) дописываются JSONL-строки; перед длинным сценарием вызвать action_json_log_recent и пропускать уже имеющиеся action_signature.",
        "2e) Если задан MCP_LEARN_JSONL — в отдельный файл дописываются наблюдения (kind=cursor_interaction, policy=none); они **не влияют** на uia_click/capture и не читаются сервером при принятии решений. learn_log_recent — только просмотр хвоста для агента.",
        "2d) Декларативные сценарии: каталог scenarios/ + scripts/run_lep_scenario.py — промпт для агента; capture_window/capture_monitor: filename_suffix или out_path (MCP_CAPTURE_DIR).",
        "2f) Автономно на ВМ без агента: один вызов lep_run_scenario(scenario_name) — выполняет весь JSON на сервере; либо scripts/execute_lep_scenario_local.py в том же venv.",
        "2g) Автообновление MCP при неверной работе из‑за старого кода на ВМ: если uia_tools_revision/protocol_version не совпадают с ожидаемыми после merge "
        "или стабильно воспроизводится исправленный в git баг — при MCP_ALLOW_SELF_UPDATE=1 и корректном MCP_REPO_ROOT вызвать server_update(mode=git_pull или full), "
        "дождаться data.restart_scheduled=true, пауза 3–10 с, снова health → agent_session (сверка ревизий), затем повторить nanocad_lep_prepare / lep_run_scenario / сценарий. "
        "Если self-update отключён — BLOCKED: обновить ВМ вручную по DEPLOY_VM_CHECKLIST.",
        "2b) LEP: перед кликами по вкладкам палитры — capture_window + capture_monitor (include_base64=true) и проверить на картинке, "
        "что панель LEP слева открыта (заголовок LEP, вкладки). Если палитры нет — клик по командной строке automation_id 1011, "
        "send_keys LEP + with_enter, снова пара снимков. Не тестировать вкладки «вслепую», если на скрине нет палитры.",
        "3) Для палитры LEP: сначала uia_list_subtree(process_name=nCAD.exe) — сохранить automation_id/name; при ERR_NOT_FOUND якоря — uia_list с большим max_nodes.",
        "4) При необходимости wait_for_element перед кликом.",
        "5) uia_click; при ошибке ERR_NOT_FOUND повторить uia_list (UI мог смениться).",
        "5b) Если на capture видна модалка (Внимание, Ошибка и т.д.), а uia_click по OK в nCAD.exe даёт ERR_NOT_FOUND — "
        "сначала uia_modal_ok (owner_process_name=nCAD.exe по умолчанию); при необходимости uia_modal_titlebar_close; "
        "для клика по области окна предпочтительнее mouse_click_window(client_x, client_y) вместо голого mouse_click от bbox; "
        "иначе mouse_move_smooth + mouse_click в экранных координатах; затем capture_window + capture_monitor.",
        "6) Передавать client_request_id (корреляция) во все инструменты — тот же id вернётся в request_id.",
        "7) ОБЯЗАТЕЛЬНО после каждого send_keys, uia_click или любого шага, меняющего экран: пара снимков — "
        "capture_window по целевому окну (обычно process_name=nCAD.exe или title_contains окна плагина) "
        "и capture_monitor (include_base64=true у обоих; при большом экране max_edge_px). "
        "Если окно не найдено — хотя бы capture_monitor с monitor_index=1; смотреть data.content_hint "
        "(likely_blank_or_no_video_output после отключения RDP без виртуального монитора). "
        "По обоим data.png_base64 подтвердить: достигнут ли ожидаемый результат шага (вкладка, панель, модалка закрыта, при необходимости виден кадр чертежа); "
        "при расхождении — не PASS и не следующий шаг; ok=true у uia_click не равно успеху теста.",
        "8) После проверки скринов — uia_list_subtree или uia_list; для LEP при truncated=true увеличить max_depth/max_nodes или сузить якорь (anchor_name_contains).",
        "9) Полная проверка UI плагина: пройти все найденные кнопки/вкладки/поля ввода из uia_list, при сомнении "
        "снова capture_window после локального действия; не пропускать модальные окна (Совет дня, ошибки NETLOAD).",
        "10) Если после команды плагина (LEP_*, NETLOAD) в дереве нет ожидаемых имён — зафиксировать и запросить "
        "у пользователя загрузку DLL/LEP.cfg; не выдумывать успех.",
    ]
    return {
        "protocol_version": PROTOCOL_VERSION,
        "server": ver,
        "tools": tools,
        "workflow": workflow,
        "lep_ui_titles_hint": [
            "LEP",
            "Кабельные",
            "палитр",
            "LEP -",
            "nanoCAD",
            "Платформа nanoCAD",
        ],
        "environment": {
            "MCP_HOST": _safe_env("MCP_HOST"),
            "MCP_PORT": _safe_env("MCP_PORT"),
            "MCP_STATELESS_HTTP": _env_bool("MCP_STATELESS_HTTP"),
            "MCP_REPO_ROOT": _safe_env("MCP_REPO_ROOT"),
            "MCP_ALLOW_SELF_UPDATE": _env_bool("MCP_ALLOW_SELF_UPDATE"),
            "MCP_RESTART_AFTER_UPDATE": _env_bool("MCP_RESTART_AFTER_UPDATE"),
            "MCP_UPDATE_USE_PS1": _env_bool("MCP_UPDATE_USE_PS1"),
            "MCP_ALLOW_LAUNCH": _env_bool("MCP_ALLOW_LAUNCH"),
            "MCP_BLOCK_LAUNCH": _env_bool("MCP_BLOCK_LAUNCH"),
            "MCP_NANOCAD_EXE": _safe_env("MCP_NANOCAD_EXE"),
            "MCP_LEP_COMMAND": _safe_env("MCP_LEP_COMMAND"),
            "MCP_ACTION_JSONL": _safe_env("MCP_ACTION_JSONL"),
            "MCP_ACTION_JSONL_FILTER": _safe_env("MCP_ACTION_JSONL_FILTER"),
            "MCP_LEARN_JSONL": _safe_env("MCP_LEARN_JSONL"),
            "MCP_LEARN_FILTER": _safe_env("MCP_LEARN_FILTER"),
            "MCP_LEARN_INCLUDE_FAILURES": _safe_env("MCP_LEARN_INCLUDE_FAILURES"),
            "MCP_CAPTURE_DIR": _safe_env("MCP_CAPTURE_DIR"),
            "MCP_MODAL_POLL_SEC": _safe_env("MCP_MODAL_POLL_SEC"),
            "cwd": os.getcwd(),
            "argv0": sys.argv[0] if sys.argv else "",
        },
        "response_contract": {
            "format": "JSON string from every tool",
            "fields": ["ok", "code", "message", "protocol_version", "request_id", "server_time_utc", "data"],
            "codes_ok": ["OK"],
            "codes_error_examples": [
                "ERR_PLATFORM",
                "ERR_VALIDATION",
                "ERR_NOT_FOUND",
                "ERR_TIMEOUT",
                "ERR_UIA",
                "ERR_UPDATE",
                "ERR_FORBIDDEN",
            ],
        },
    }

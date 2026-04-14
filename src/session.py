"""Снимок состояния сервера для агента: возможности, шаги коммуникации, безопасные env-флаги."""

from __future__ import annotations

import os
import sys
from typing import Any

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
    tools = [
        {"name": "health", "role": "проверка живости; всегда вызывать первым при сомнениях в сети"},
        {"name": "agent_session", "role": "этот снимок: версия протокола, шаги, env"},
        {"name": "server_info", "role": "краткая версия/git/python"},
        {"name": "server_update", "role": "обновление pip/git; только при MCP_ALLOW_SELF_UPDATE=1"},
        {"name": "uia_list", "role": "дерево UI в JSON (data.items); смотреть data.truncated"},
        {
            "name": "uia_click",
            "role": "клик по селектору; сразу после — capture_window + uia_list (см. workflow)",
        },
        {"name": "wait_for_element", "role": "ожидание элемента; ERR_TIMEOUT если не дождались"},
        {
            "name": "send_keys",
            "role": "ввод текста в окно; сразу после — capture_window + uia_list (см. workflow)",
        },
        {
            "name": "capture_window",
            "role": "Снимок окна: data.png_base64 (include_base64=true) — обязателен после действий; визуально проверить результат",
        },
        {
            "name": "capture_monitor",
            "role": "Снимок целого монитора (MSS); при отключённом RDP без виртуального дисплея смотреть data.content_hint",
        },
        {
            "name": "launch_process",
            "role": "Запуск .exe; отключить: MCP_BLOCK_LAUNCH=1. executable=AUTO_NANOCAD — поиск nCAD.exe",
        },
    ]
    workflow = [
        "1) Вызвать health — убедиться, что JSON парсится и ok=true.",
        "2) Вызвать agent_session — прочитать protocol_version и рекомендуемые инструменты.",
        "3) uia_list с process_name или title_contains — сохранить automation_id для цели.",
        "4) При необходимости wait_for_element перед кликом.",
        "5) uia_click; при ошибке ERR_NOT_FOUND повторить uia_list (UI мог смениться).",
        "6) Передавать client_request_id (корреляция) во все инструменты — тот же id вернётся в request_id.",
        "7) ОБЯЗАТЕЛЬНО после каждого send_keys, uia_click или любого шага, меняющего экран: capture_window "
        "по целевому окну (обычно process_name=nCAD.exe или title_contains окна плагина), "
        "include_base64=true, при большом экране задать max_edge_px. Если нужен весь рабочий стол без окна "
        "(например процесс не найден) — capture_monitor с monitor_index=1; смотреть data.content_hint "
        "(likely_blank_or_no_video_output после отключения RDP без виртуального монитора). "
        "Агент проверяет data.png_base64 и сопоставляет с ожидаемым; при расхождении не продолжать вслепую.",
        "8) После каждого снимка — uia_list того же контекста; для UI плагина LEP дополнительно опросить окна по "
        "title_contains: «LEP», «Кабельные», «палитр», «LEP -» (регистр как в ОС). Цель — полностью описать "
        "доступные элементы панелей/форм; при data.truncated=true увеличить max_depth и max_nodes и повторить.",
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
            "MCP_UPDATE_USE_PS1": _env_bool("MCP_UPDATE_USE_PS1"),
            "MCP_ALLOW_LAUNCH": _env_bool("MCP_ALLOW_LAUNCH"),
            "MCP_BLOCK_LAUNCH": _env_bool("MCP_BLOCK_LAUNCH"),
            "MCP_NANOCAD_EXE": _safe_env("MCP_NANOCAD_EXE"),
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

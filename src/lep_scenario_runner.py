"""
Выполнение JSON-сценария LEP: общая логика для MCP-инструмента lep_run_scenario и скрипта execute_lep_scenario_local.

На не-Windows модуль импортируется только для валидации JSON (без вызова server).
"""

from __future__ import annotations

import inspect
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

ALLOWED_INVOKES = frozenset(
    {
        "health",
        "agent_session",
        "lep_qa_catalog",
        "server_info",
        "server_update",
        "uia_list",
        "uia_list_subtree",
        "uia_click",
        "wait_for_element",
        "uia_modal_ok",
        "uia_modal_titlebar_close",
        "mouse_click",
        "mouse_click_window",
        "mouse_move",
        "mouse_move_smooth",
        "send_keys",
        "capture_window",
        "capture_monitor",
        "launch_process",
        "nanocad_lep_prepare",
        "action_json_log_recent",
        "learn_log_recent",
    }
)


def load_scenario_dict(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Корень JSON должен быть объектом")
    return data


def validate_scenario(data: dict[str, Any], path: Path | str) -> None:
    for key in ("id", "title", "version"):
        if key not in data:
            raise ValueError(f"Отсутствует обязательное поле: {key} ({path})")
    if int(data["version"]) != 1:
        raise ValueError(f"Поддерживается только version=1, получено: {data['version']}")
    sofe = data.get("stop_on_first_error")
    if sofe is not None and not isinstance(sofe, bool):
        raise ValueError("stop_on_first_error должен быть boolean, если задан")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Нужен непустой массив steps")
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Шаг {i}: ожидается объект")
        inv = step.get("invoke")
        if not inv or not isinstance(inv, str):
            raise ValueError(f"Шаг {i}: нужен invoke (строка)")
        if inv not in ALLOWED_INVOKES:
            raise ValueError(
                f"Шаг {i}: неизвестный invoke «{inv}». Допустимы: {sorted(ALLOWED_INVOKES)}"
            )
        args = step.get("args")
        if args is not None and not isinstance(args, dict):
            raise ValueError(f"Шаг {i}: args должен быть объектом")


def _bind_and_call(fn: Callable[..., str], args: dict[str, Any] | None, request_id: str | None) -> str:
    sig = inspect.signature(fn)
    kwargs: dict[str, Any] = {}
    if args:
        for k, v in args.items():
            if k in sig.parameters:
                kwargs[k] = v
    if "client_request_id" in sig.parameters:
        kwargs.setdefault("client_request_id", request_id)
    return fn(**kwargs)


def parse_tool_json(raw: str) -> dict[str, Any]:
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def run_scenario_json(
    data: dict[str, Any],
    *,
    get_tool: Callable[[str], Callable[..., str]],
    id_prefix: str,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Выполняет steps по порядку. get_tool(name) -> callable MCP tool returning JSON string.

    Если в корне сценария ``stop_on_first_error: false`` — после ошибки шага выполнение продолжается;
    в конце ``all_ok`` ложен, если хотя бы один шаг не ``ok``.

    Returns (all_ok, step_log).
    """
    if sys.platform != "win32":
        return False, [{"error": "ERR_PLATFORM", "message": "run_scenario_json только на Windows"}]

    stop_on_first_error = data.get("stop_on_first_error", True)
    if not isinstance(stop_on_first_error, bool):
        stop_on_first_error = True

    log: list[dict[str, Any]] = []
    prefix = (id_prefix or "lep_run")[:48]
    for i, step in enumerate(data["steps"], start=1):
        inv = step["invoke"]
        rid = step.get("client_request_id") or f"{prefix}-s{i}-{uuid.uuid4().hex[:10]}"
        step_args = step.get("args")
        fn = get_tool(inv)
        raw = _bind_and_call(fn, step_args, rid)
        body = parse_tool_json(raw)
        ok = body.get("ok") is True
        entry: dict[str, Any] = {
            "n": i,
            "invoke": inv,
            "ok": ok,
            "code": body.get("code"),
            "request_id": body.get("request_id", rid),
        }
        if not ok:
            entry["message"] = body.get("message")
            entry["raw_excerpt"] = (raw or "")[:800]
        log.append(entry)
        if not ok and stop_on_first_error:
            return False, log
    all_ok = all(bool(e.get("ok")) for e in log)
    return all_ok, log


def resolve_scenario_path_under_root(scenario_name: str, scenarios_root: Path) -> Path:
    """Только файлы под scenarios_root (защита от path traversal)."""
    root = scenarios_root.resolve()
    raw = (scenario_name or "").strip().replace("\\", "/")
    if ".." in raw or raw.startswith("/"):
        raise ValueError("Недопустимое имя сценария")
    p = (root / raw).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ValueError("Сценарий вне каталога scenarios") from e
    if not p.is_file():
        p2 = p.with_suffix(".json")
        if p2.is_file():
            return p2
        raise FileNotFoundError(str(p))
    if p.suffix.lower() != ".json":
        raise ValueError("Ожидается .json")
    return p

"""
Корпус наблюдений для будущего offline-распознавания (observe_only, policy=none).

Включение: **MCP_LEARN_JSONL** — путь к append-only JSONL. Сервер **не** читает этот файл
при выполнении UIA/capture и **не** меняет ветвления инструментов.

Фильтр **MCP_LEARN_FILTER**: `lep_only` (по умолчанию) | `all` — та же эвристика, что у action log.
**MCP_LEARN_INCLUDE_FAILURES**: `1` — писать также записи с `ok=false` (для обучения на ошибках).
"""

from __future__ import annotations

import json
import os
from typing import Any

from src.action_json_log import _ts_iso, is_lep_related_tool, sanitize_tool_params, tool_response_summary

LEARN_SCHEMA_VERSION = 1


def _learn_path() -> str | None:
    p = (os.environ.get("MCP_LEARN_JSONL") or "").strip()
    return p if p else None


def _learn_filter() -> str:
    v = (os.environ.get("MCP_LEARN_FILTER") or "lep_only").strip().lower()
    return v if v in ("lep_only", "all") else "lep_only"


def _learn_include_failures() -> bool:
    return os.environ.get("MCP_LEARN_INCLUDE_FAILURES", "").strip().lower() in ("1", "true", "yes")


def try_log_observation(tool: str, params: dict[str, Any], result_json: str) -> None:
    path = _learn_path()
    if not path:
        return
    try:
        body = json.loads(result_json)
    except Exception:
        return
    if not isinstance(body, dict):
        return
    ok = body.get("ok") is True
    if not ok and not _learn_include_failures():
        return
    if _learn_filter() == "lep_only" and not is_lep_related_tool(tool, params):
        return

    entry: dict[str, Any] = {
        "schema_version": LEARN_SCHEMA_VERSION,
        "kind": "cursor_interaction",
        "policy": "none",
        "logged_at_utc": _ts_iso(),
        "tool": tool,
        "ok": ok,
        "code": body.get("code"),
        "request_id": body.get("request_id"),
        "protocol_version": body.get("protocol_version"),
        "params": sanitize_tool_params(params),
        "response_summary": tool_response_summary(tool, body),
    }
    if not ok:
        msg = body.get("message")
        if isinstance(msg, str) and msg:
            entry["message_excerpt"] = msg[:400]

    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        return


def read_recent_entries(max_lines: int = 40) -> tuple[bool, str, list[dict[str, Any]]]:
    """Последние max_lines JSON-объектов из MCP_LEARN_JSONL."""
    path = _learn_path()
    if not path:
        return False, "MCP_LEARN_JSONL не задан", []
    cap = max(1, min(int(max_lines), 200))
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        return False, str(e), []
    tail = lines[-cap:]
    out: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError:
            continue
    return True, "OK", out

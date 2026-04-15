"""
Дополнительное JSONL-логирование успешных вызовов MCP (одна JSON-строка = одна запись).

Включение: задать MCP_ACTION_JSONL — путь к файлу (append). Пусто — логирование выключено.

Фильтр MCP_ACTION_JSONL_FILTER:
  lep_only (по умолчанию) — только шаги, связанные с nanoCAD / LEP / модалками / подготовкой сеанса;
  all — любой инструмент с ok=true.

Записи можно агрегировать по полю action_signature, чтобы не повторять уже выполненные шаги в сценарии.

Отдельный корпус наблюдений (**MCP_LEARN_JSONL**) пишет модуль **learn_log** из того же декоратора; он не влияет на replay.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

_MAX_PARAM_STR = 512
_SENSITIVE_KEYS = frozenset(
    k.lower()
    for k in (
        "MCP_AUTH_TOKEN",
        "Authorization",
        "password",
        "token",
        "secret",
        "png_base64",
    )
)


def _ts_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_filter() -> str:
    v = (os.environ.get("MCP_ACTION_JSONL_FILTER") or "lep_only").strip().lower()
    return v if v in ("lep_only", "all") else "lep_only"


def _log_path() -> str | None:
    p = (os.environ.get("MCP_ACTION_JSONL") or "").strip()
    return p if p else None


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in sorted(params.items()):
        lk = k.lower()
        if any(s in lk for s in _SENSITIVE_KEYS):
            out[k] = "<redacted>"
            continue
        if v is None:
            continue
        if isinstance(v, str):
            if len(v) > _MAX_PARAM_STR:
                out[k] = v[:_MAX_PARAM_STR] + "…"
            else:
                out[k] = v
        elif isinstance(v, (int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)[:_MAX_PARAM_STR]
    return out


def _norm_process(name: str | None) -> str:
    return (name or "").strip().lower()


def _is_lep_related_tool(tool: str, params: dict[str, Any]) -> bool:
    """Эвристика: что считать «действием с плагином / CAD»."""
    if tool in (
        "nanocad_lep_prepare",
        "uia_list_subtree",
        "uia_modal_ok",
        "uia_modal_titlebar_close",
    ):
        return True
    if tool == "launch_process":
        ex = (params.get("executable") or "").strip().upper()
        if ex in ("AUTO", "AUTO_NANOCAD"):
            return True
        low = (params.get("executable") or "").lower()
        return low.endswith("ncad.exe") or "nanosoft" in low
    proc = _norm_process(params.get("process_name"))  # type: ignore[arg-type]
    aid = (params.get("automation_id") or "").strip().lower()
    nm = (params.get("name") or "").strip().lower()
    if tool == "uia_list":
        return proc == "ncad.exe" or "lep" in (params.get("title_contains") or "").lower()
    if tool == "uia_click":
        if aid.startswith("lep_") or aid in ("1011",):
            return True
        if proc == "ncad.exe":
            return True
        if "lep" in nm:
            return True
    if tool == "wait_for_element":
        if aid.startswith("lep_"):
            return True
        if proc == "ncad.exe":
            return True
    if tool == "send_keys":
        return proc in ("", "ncad.exe")
    if tool in ("mouse_click_window",):
        return proc == "ncad.exe"
    if tool in ("mouse_click", "mouse_move", "mouse_move_smooth"):
        return False
    if tool in ("capture_window", "capture_monitor"):
        return proc == "ncad.exe" or bool((params.get("title_contains") or "").strip())
    if tool in ("health", "agent_session", "server_info", "server_update"):
        return False
    return False


def _response_summary(tool: str, body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    if not isinstance(data, dict):
        return {}
    keys_keep = (
        "closed",
        "via",
        "clicked_index",
        "matches_total",
        "found",
        "waited_sec",
        "palette_ready",
        "skipped_command_input",
        "sent",
        "executable",
        "process_name",
        "truncated",
        "items_count",
        "hwnd",
        "owner_hwnd",
        "button",
        "size",
    )
    summary: dict[str, Any] = {}
    for k in keys_keep:
        if k in data:
            summary[k] = data[k]
    if tool == "uia_list_subtree" and "items" in data:
        summary["items_count"] = len(data["items"]) if isinstance(data["items"], list) else None
    if tool == "uia_list" and "items" in data:
        summary["items_count"] = len(data["items"]) if isinstance(data["items"], list) else None
    if tool == "nanocad_lep_prepare" and isinstance(data.get("steps"), list):
        summary["steps_count"] = len(data["steps"])
    if tool in ("capture_window", "capture_monitor"):
        for k in ("path", "content_hint", "bbox", "filename_suffix", "monitor_index", "monitors_count"):
            if k in data:
                summary[k] = data[k]
    return summary


def sanitize_tool_params(params: dict[str, Any]) -> dict[str, Any]:
    """Публичная обёртка для learn_log и внешних скриптов."""
    return _sanitize_params(params)


def is_lep_related_tool(tool: str, params: dict[str, Any]) -> bool:
    """Та же эвристика, что для MCP_ACTION_JSONL_FILTER=lep_only."""
    return _is_lep_related_tool(tool, params)


def tool_response_summary(tool: str, body: dict[str, Any]) -> dict[str, Any]:
    """Краткое содержимое data из ответа инструмента (без base64)."""
    return _response_summary(tool, body)


def _replay_hint(tool: str, params: dict[str, Any]) -> str:
    parts = [tool]
    if params.get("process_name"):
        parts.append(str(params["process_name"]))
    for key in ("automation_id", "name", "title_contains", "anchor_automation_id", "lep_command"):
        if params.get(key):
            parts.append(f"{key}={params[key]}")
    if params.get("text") is not None and tool == "send_keys":
        parts.append("send_keys")
    return " ".join(parts)[:300]


def _action_signature(tool: str, params: dict[str, Any]) -> str:
    """Стабильный короткий идентификатор шага для дедупликации сценариев."""
    san = sanitize_tool_params({k: v for k, v in params.items() if k != "client_request_id"})
    raw = json.dumps({"tool": tool, "params": san}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def try_log_successful_tool(tool: str, params: dict[str, Any], result_json: str) -> None:
    path = _log_path()
    if not path:
        return
    try:
        body = json.loads(result_json)
    except Exception:
        return
    if not isinstance(body, dict) or body.get("ok") is not True:
        return
    if _env_filter() == "lep_only" and not _is_lep_related_tool(tool, params):
        return
    entry = {
        "logged_at_utc": _ts_iso(),
        "tool": tool,
        "request_id": body.get("request_id"),
        "action_signature": _action_signature(tool, params),
        "replay_hint": _replay_hint(tool, params),
        "params": sanitize_tool_params(params),
        "response_summary": _response_summary(tool, body),
        "protocol_version": body.get("protocol_version"),
    }
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
    """
    Прочитать последние max_lines JSON-объектов из MCP_ACTION_JSONL (с конца файла).
    Возвращает (ok, message_or_code, list).
    """
    path = _log_path()
    if not path:
        return False, "MCP_ACTION_JSONL не задан", []
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


def tool_log_decorator(tool_name: str):
    """Оборачивает MCP-инструмент: после ok=true дописывает строку в MCP_ACTION_JSONL."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            out = fn(*args, **kwargs)
            try:
                try_log_successful_tool(tool_name, dict(kwargs), out)
            except Exception:
                pass
            try:
                from src import learn_log as _learn_log

                _learn_log.try_log_observation(tool_name, dict(kwargs), out)
            except Exception:
                pass
            return out

        return wrapped

    return decorator

"""
Единый контракт ответов MCP-инструментов — всегда валидный JSON-объект (строка в теле tool).

Агент должен парсить верхний уровень и ветвиться по `ok` / `code`.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = "1.7"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def envelope(
    ok: bool,
    code: str,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    rid = request_id or str(uuid.uuid4())
    return {
        "ok": ok,
        "code": code,
        "message": message,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": rid,
        "server_time_utc": _ts(),
        "data": data if data is not None else {},
    }


def ok_json(
    code: str = "OK",
    message: str = "",
    data: dict[str, Any] | None = None,
    *,
    request_id: str | None = None,
) -> str:
    return json.dumps(
        envelope(True, code, message or "success", data, request_id=request_id),
        ensure_ascii=False,
        indent=2,
    )


def err_json(
    code: str,
    message: str,
    *,
    data: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> str:
    payload = data or {}
    return json.dumps(
        envelope(False, code, message, payload, request_id=request_id),
        ensure_ascii=False,
        indent=2,
    )


def parse_request_id(raw: str | None) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip()[:128]

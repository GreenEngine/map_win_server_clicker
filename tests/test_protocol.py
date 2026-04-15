"""Парсинг JSON-конверта ответов инструментов (protocol.ok_json)."""

from __future__ import annotations

import json

from src.protocol import PROTOCOL_VERSION, ok_json


def test_ok_json_parses_and_has_envelope_keys() -> None:
    raw = ok_json(data={"check": True}, message="unit", request_id="req-test-1")
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["request_id"] == "req-test-1"
    assert payload["data"] == {"check": True}
    assert "code" in payload
    assert "message" in payload
    assert "server_time_utc" in payload

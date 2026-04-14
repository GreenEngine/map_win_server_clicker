"""
LEP Windows MCP server: Streamable HTTP + UI Automation tools + self-update.

Каждый инструмент возвращает строку с **валидным JSON** (конверт protocol):
ok, code, message, protocol_version, request_id, server_time_utc, data.

Запуск (на Windows):
  set MCP_HOST=0.0.0.0
  set MCP_PORT=8765
  python src/server.py
"""

from __future__ import annotations

import os
import socket
import sys

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from mcp.server.fastmcp import FastMCP

from src import uia_tools
from src import session as session_mod
from src import update as update_mod
from src.protocol import err_json, ok_json, parse_request_id

_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
_PORT = int(os.environ.get("MCP_PORT", "8765"))
_STATELESS = os.environ.get("MCP_STATELESS_HTTP", "").lower() in ("1", "true", "yes")

# server_update: если переменная не задана или пустая — по умолчанию разрешено. Явно 0/false/no — отключение.
_mcp_su = os.environ.get("MCP_ALLOW_SELF_UPDATE")
if _mcp_su is None or str(_mcp_su).strip() == "":
    os.environ["MCP_ALLOW_SELF_UPDATE"] = "1"

# launch_process: по умолчанию ВКЛ (часто в среде уже стоит MCP_ALLOW_LAUNCH=0 из старых скриптов).
# Явный запрет только: MCP_BLOCK_LAUNCH=1 (или true / yes).
if os.environ.get("MCP_BLOCK_LAUNCH", "").strip().lower() in ("1", "true", "yes"):
    os.environ["MCP_ALLOW_LAUNCH"] = "0"
else:
    os.environ["MCP_ALLOW_LAUNCH"] = "1"

mcp = FastMCP(
    "LEP Windows UI MCP",
    host=_HOST,
    port=_PORT,
    stateless_http=_STATELESS,
    streamable_http_path="/mcp",
)


@mcp.tool()
def health(client_request_id: str | None = None) -> str:
    """Проверка связи: всегда ok=true при живом процессе. Вызывайте первым."""
    rid = parse_request_id(client_request_id)
    return ok_json(
        data={"status": "alive", "host": _HOST, "port": _PORT},
        message="health",
        request_id=rid,
    )


@mcp.tool()
def agent_session(client_request_id: str | None = None) -> str:
    """Снимок для агента: protocol_version, список инструментов, workflow, безопасные env, контракт ответов."""
    rid = parse_request_id(client_request_id)
    return ok_json(data=session_mod.agent_session_payload(), message="agent_session", request_id=rid)


@mcp.tool()
def server_info(client_request_id: str | None = None) -> str:
    """Версия Python, пути, git — внутри data (плоская структура)."""
    rid = parse_request_id(client_request_id)
    return ok_json(data=update_mod.server_version_dict(), message="server_info", request_id=rid)


@mcp.tool()
def server_update(mode: str = "pip", client_request_id: str | None = None) -> str:
    """
    Обновление: pip / git_pull / full. Требует MCP_ALLOW_SELF_UPDATE=1.
    Лог в data.log; при ошибке ok=false, code=ERR_UPDATE.
    """
    rid = parse_request_id(client_request_id)
    ok, log = update_mod.run_self_update(mode)
    if ok:
        return ok_json(data={"log": log, "mode": mode}, message="server_update", request_id=rid)
    code = "ERR_FORBIDDEN" if "отключ" in (log or "").lower() else "ERR_UPDATE"
    return err_json(code, log or "update failed", data={"log": log, "mode": mode}, request_id=rid)


@mcp.tool()
def uia_list(
    process_name: str | None = None,
    title_contains: str | None = None,
    max_depth: int = 6,
    max_nodes: int = 400,
    client_request_id: str | None = None,
) -> str:
    """Список элементов UI (JSON-конверт, элементы в data.items)."""
    return uia_tools.uia_list(process_name, title_contains, max_depth, max_nodes, client_request_id)


@mcp.tool()
def uia_click(
    process_name: str | None = None,
    title_contains: str | None = None,
    automation_id: str | None = None,
    name: str | None = None,
    control_type: str | None = None,
    nth: int = 0,
    client_request_id: str | None = None,
) -> str:
    """Клик по элементу (nth при нескольких совпадениях)."""
    return uia_tools.uia_click(
        process_name,
        title_contains,
        automation_id,
        name,
        control_type,
        nth,
        client_request_id,
    )


@mcp.tool()
def wait_for_element(
    process_name: str | None = None,
    title_contains: str | None = None,
    automation_id: str | None = None,
    name: str | None = None,
    timeout_sec: float = 30.0,
    client_request_id: str | None = None,
) -> str:
    """Ждать появления элемента; при таймауте code=ERR_TIMEOUT."""
    return uia_tools.wait_for(
        process_name,
        title_contains,
        automation_id,
        name,
        timeout_sec,
        0.5,
        client_request_id,
    )


@mcp.tool()
def send_keys(
    process_name: str | None = None,
    title_contains: str | None = None,
    text: str = "",
    with_enter: bool = False,
    client_request_id: str | None = None,
) -> str:
    """Ввод текста в окно."""
    return uia_tools.send_keys(process_name, title_contains, text, with_enter, client_request_id)


@mcp.tool()
def capture_window(
    process_name: str | None = None,
    title_contains: str | None = None,
    out_path: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    """
    PNG снимок окна: data.path на Windows.
    При include_base64=True в data.png_base64 — картинка для удалённого клиента (Mac и т.д.).
    max_edge_px>0 ограничивает большую сторону встраиваемого PNG; файл на диске — полный кадр.
    """
    return uia_tools.capture_window(
        process_name,
        title_contains,
        out_path,
        include_base64,
        max_edge_px,
        client_request_id,
    )


@mcp.tool()
def launch_process(
    executable: str,
    arguments: str = "",
    wait_timeout_sec: float = 90.0,
    client_request_id: str | None = None,
) -> str:
    """
    Запуск .exe на Windows. Нужен MCP_ALLOW_LAUNCH=1 на сервере.
    executable: полный путь или AUTO / AUTO_NANOCAD (поиск nCAD.exe).
    После старта ждёт появления процесса в UIA (до wait_timeout_sec).
    """
    return uia_tools.launch_process(executable, arguments, wait_timeout_sec, client_request_id)


@mcp.tool()
def capture_monitor(
    monitor_index: int = 1,
    out_path: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    """
    Снимок всего монитора (MSS), без привязки к окну процесса.
    monitor_index: 0 — все мониторы одним кадром, 1 — основной (часто нужен он).
    Если после отключения RDP кадр чёрный — смотрите data.content_hint и README (виртуальный дисплей).
    """
    return uia_tools.capture_monitor(
        monitor_index,
        out_path,
        include_base64,
        max_edge_px,
        client_request_id,
    )


def _local_ipv4_candidates() -> list[str]:
    """IPv4 этой машины без loopback (для лога при старте)."""
    order: list[str] = []
    seen: set[str] = set()

    def add(ip: str) -> None:
        if not ip or ip.startswith("127."):
            return
        if ip not in seen:
            seen.add(ip)
            order.append(ip)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            add(info[4][0])
    except OSError:
        pass
    return order


def _print_listen_banner() -> None:
    ips = _local_ipv4_candidates()
    path = getattr(mcp, "streamable_http_path", None) or "/mcp"
    bind = f"{_HOST}:{_PORT}"
    print(f"[MCP] Слушаю {bind}, путь {path}", flush=True)
    if ips:
        joined = ", ".join(ips)
        print(f"[MCP] IPv4 этой машины: {joined}", flush=True)
        if _HOST in ("0.0.0.0", "::"):
            primary = ips[0]
            print(f"[MCP] Пример URL для клиента в сети: http://{primary}:{_PORT}{path}", flush=True)
    else:
        print("[MCP] Не удалось определить IPv4 (смотрите ipconfig / ifconfig).", flush=True)


def main() -> None:
    _print_listen_banner()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Ждёт завершения родительского процесса MCP, затем снова запускает src/server.py.

Вызывается из update.schedule_restart_after_update (отдельный процесс, чтобы
освободить порт после os._exit в родителе).

Аргументы: <parent_pid> <python_exe> <server_py> <cwd>

Переменные окружения:
  MCP_RESTART_LOG — файл для журнала helper (иначе <cwd>/logs/mcp_restart_helper.log).
  MCP_HOST / MCP_PORT — для ожидания освобождения порта перед запуском нового процесса.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_log_file(cwd: str) -> Path:
    raw = (os.environ.get("MCP_RESTART_LOG") or "").strip()
    if raw:
        return Path(raw).expanduser()
    d = Path(cwd) / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "mcp_restart_helper.log"


def _log(path: Path, msg: str) -> None:
    line = f"{_ts()} {msg}\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        try:
            print(line, end="", file=sys.stderr)
        except Exception:
            pass


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return str(pid) in (out.stdout or "")
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tcp_port_in_use(host: str, port: int) -> bool:
    """True, если на host:port что-то принимает TCP (старый MCP ещё слушает)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            err = s.connect_ex((host, port))
            return err == 0
        finally:
            s.close()
    except Exception:
        return False


def _wait_port_free(log: Path, host: str, port: int, timeout_sec: float = 75.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not _tcp_port_in_use(host, port):
            _log(log, f"port {host}:{port} appears free (connect_ex != success)")
            return
        time.sleep(0.35)
    _log(log, f"WARN: port {host}:{port} still in use after {timeout_sec}s; will try start anyway")


def main() -> None:
    if len(sys.argv) < 5:
        print(
            "usage: mcp_restart_after_update.py <parent_pid> <python_exe> <server_py> <cwd>",
            file=sys.stderr,
        )
        sys.exit(2)
    parent_pid = int(sys.argv[1])
    python_exe = sys.argv[2]
    server_py = sys.argv[3]
    cwd = sys.argv[4]
    log = _resolve_log_file(cwd)
    _log(log, f"helper start parent_pid={parent_pid} python={python_exe} server={server_py} cwd={cwd}")

    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline and _pid_running(parent_pid):
        time.sleep(0.25)
    _log(log, f"parent wait done running={_pid_running(parent_pid)}")
    time.sleep(0.5)

    host = (os.environ.get("MCP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    try:
        port = int(os.environ.get("MCP_PORT", "8765"))
    except ValueError:
        port = 8765
    _wait_port_free(log, host, port)

    env = os.environ.copy()
    cf = 0
    if sys.platform == "win32":
        cf = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        cf |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        cf |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

    server_log = Path(cwd) / "logs" / "mcp_server_stderr.log"
    stderr_arg: object = subprocess.DEVNULL
    log_note = "DEVNULL"
    try:
        server_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_arg = open(server_log, "a", encoding="utf-8")
        log_note = str(server_log)
    except Exception:
        pass

    try:
        for attempt in range(1, 4):
            try:
                subprocess.Popen(
                    [python_exe, server_py],
                    cwd=cwd,
                    env=env,
                    creationflags=cf if sys.platform == "win32" else 0,
                    start_new_session=sys.platform != "win32",
                    close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_arg,
                )
                _log(log, f"server Popen ok attempt={attempt} stderr->{log_note}")
                return
            except Exception as e:
                _log(log, f"Popen failed attempt={attempt}: {e!r}")
                time.sleep(3.0)
    finally:
        if hasattr(stderr_arg, "close"):
            try:
                stderr_arg.close()
            except Exception:
                pass
    _log(log, "FATAL: all Popen retries failed")
    sys.exit(1)


if __name__ == "__main__":
    main()

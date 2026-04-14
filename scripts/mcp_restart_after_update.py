#!/usr/bin/env python3
"""
Ждёт завершения родительского процесса MCP, затем снова запускает src/server.py.

Вызывается из update.schedule_restart_after_update (отдельный процесс, чтобы
освободить порт после os._exit в родителе).

Аргументы: <parent_pid> <python_exe> <server_py> <cwd>
"""

from __future__ import annotations

import os
import subprocess
import sys
import time


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


def main() -> None:
    if len(sys.argv) < 5:
        print("usage: mcp_restart_after_update.py <parent_pid> <python_exe> <server_py> <cwd>", file=sys.stderr)
        sys.exit(2)
    parent_pid = int(sys.argv[1])
    python_exe = sys.argv[2]
    server_py = sys.argv[3]
    cwd = sys.argv[4]

    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline and _pid_running(parent_pid):
        time.sleep(0.25)
    time.sleep(0.5)

    env = os.environ.copy()
    cf = 0
    if sys.platform == "win32":
        cf = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        cf |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        cf |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

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
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"mcp_restart_after_update: failed to start server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

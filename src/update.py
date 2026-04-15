"""Self-update helpers for the MCP server (gated by MCP_ALLOW_SELF_UPDATE)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _server_root() -> Path:
    """Каталог пакета windows-mcp-server (рядом с src/)."""
    return Path(__file__).resolve().parent.parent


def _repo_root() -> Path:
    """
    Корень git для `git pull`.
    - Явно: MCP_REPO_ROOT.
    - Иначе: если есть `.git` внутри windows-mcp-server — он; иначе если `.git` у родителя (монорепо LEP) — родитель.
    Раньше по ошибке брался только родитель каталога сервера → на Desktop искали Desktop\\.git, а не windows-mcp-server\\.git.
    """
    env = os.environ.get("MCP_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    srv = _server_root()
    if (srv / ".git").is_dir():
        return srv
    parent = srv.parent
    if (parent / ".git").is_dir():
        return parent
    return srv


def server_version_dict() -> dict[str, Any]:
    srv = _server_root()
    rev = ""
    try:
        p = subprocess.run(
            ["git", "-C", str(_repo_root()), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if p.returncode == 0:
            rev = p.stdout.strip()
    except Exception:
        pass
    return {
        "server_root": str(srv),
        "repo_root": str(_repo_root()),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "git_short": rev or None,
        "summary": f"windows-mcp-server root={srv}; python={sys.version.split()[0]}; git={rev or 'n/a'}",
    }


def _restart_after_update_enabled() -> bool:
    """По умолчанию после успешного обновления планируется перезапуск процесса MCP."""
    v = os.environ.get("MCP_RESTART_AFTER_UPDATE", "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    return True


def schedule_parent_exit_only(delay_sec: float = 2.5) -> None:
    """
    Только завершить текущий процесс MCP после паузы (ответ клиенту успевает уйти).
    Используется, когда перезапуск уже инициирован извне (например update_server.ps1).
    """

    def _exit_only() -> None:
        try:
            time.sleep(float(delay_sec))
            os._exit(0)
        except Exception:
            pass

    threading.Thread(target=_exit_only, daemon=True).start()


def schedule_restart_after_update() -> None:
    """
    Через ~1.5 с после ответа клиенту: старт `scripts/mcp_restart_after_update.py`, затем os._exit(0).
    Новый процесс ждёт освобождения порта (завершения старого PID), затем запускает `src/server.py`.
    """
    if not _restart_after_update_enabled():
        return
    srv = _server_root()
    helper = srv / "scripts" / "mcp_restart_after_update.py"
    server_py = srv / "src" / "server.py"
    if not helper.is_file() or not server_py.is_file():
        return

    python_exe = sys.executable
    pid = os.getpid()
    cwd = str(srv)

    def _restart() -> None:
        try:
            time.sleep(2.0)
            cf = 0
            if sys.platform == "win32":
                cf = int(getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
                cf |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
            subprocess.Popen(
                [python_exe, str(helper), str(pid), python_exe, str(server_py), cwd],
                cwd=cwd,
                creationflags=cf if sys.platform == "win32" else 0,
                start_new_session=sys.platform != "win32",
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            os._exit(0)
        except Exception:
            pass

    threading.Thread(target=_restart, daemon=True).start()


def run_self_update(mode: str = "pip") -> tuple[bool, str, bool]:
    """
    Returns:
        (success, log_text, restart_scheduled)
    """
    if os.environ.get("MCP_ALLOW_SELF_UPDATE", "").strip() not in ("1", "true", "True", "yes", "YES"):
        return (
            False,
            "Self-update отключён. Установите MCP_ALLOW_SELF_UPDATE=1 и перезапустите процесс MCP.",
            False,
        )

    root = _repo_root()
    srv = _server_root()
    req = srv / "requirements.txt"
    if not req.is_file():
        return False, f"Не найден {req}", False

    lines: list[str] = []
    restart_scheduled = False

    def run(cmd: list[str], cwd: Path | None = None) -> None:
        lines.append(f"$ {' '.join(cmd)} (cwd={cwd or Path.cwd()})")
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if p.stdout:
            lines.append(p.stdout.strip())
        if p.stderr:
            lines.append("stderr:\n" + p.stderr.strip())
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}")

    mode_l = (mode or "pip").lower().strip()
    try:
        if (
            sys.platform == "win32"
            and os.environ.get("MCP_UPDATE_USE_PS1", "").strip().lower() not in ("0", "false", "no")
        ):
            ps1 = _server_root() / "scripts" / "update_server.ps1"
            if ps1.is_file():
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps1),
                    "-RepoRoot",
                    str(root),
                ]
                if mode_l == "pip":
                    cmd.append("-SkipGit")
                want_ps_restart = _restart_after_update_enabled()
                helper = srv / "scripts" / "mcp_restart_after_update.py"
                server_py = srv / "src" / "server.py"
                if want_ps_restart and helper.is_file() and server_py.is_file():
                    cmd.extend(
                        [
                            "-McpParentPid",
                            str(os.getpid()),
                            "-PythonExe",
                            sys.executable,
                        ]
                    )
                run(cmd, cwd=_server_root())
                lines.append("Скрипт update_server.ps1 выполнен.")
                if want_ps_restart and helper.is_file() and server_py.is_file():
                    # Перезапуск стартовал из PowerShell (Start-Process → mcp_restart_after_update.py);
                    # здесь только корректно завершаем родительский процесс после ответа клиенту.
                    schedule_parent_exit_only(2.5)
                    restart_scheduled = True
                    lines.append("Перезапуск MCP: helper из update_server.ps1; процесс сервера завершится через ~2.5 с.")
                elif want_ps_restart:
                    schedule_restart_after_update()
                    restart_scheduled = True
                    lines.append("Перезапуск процесса MCP запланирован (через ~2 с, встроенный helper).")
                else:
                    lines.append("Перезапустите процесс MCP вручную, чтобы подтянуть новые .py.")
                return True, "\n".join(lines), restart_scheduled
            lines.append(f"Нет скрипта {ps1}, выполняем встроенное обновление…")

        if mode_l in ("git_pull", "full"):
            git_dir = root / ".git"
            if git_dir.exists():
                run(["git", "pull", "--ff-only"], cwd=root)
            else:
                lines.append(f"Пропуск git pull: нет {git_dir}")

        if mode_l in ("pip", "full", "git_pull"):
            run([sys.executable, "-m", "pip", "install", "-r", str(req)])

        lines.append("Готово.")
        if _restart_after_update_enabled():
            schedule_restart_after_update()
            restart_scheduled = True
            lines.append("Перезапуск процесса MCP запланирован (через ~2 с).")
        else:
            lines.append(
                "Перезапустите процесс MCP на Windows вручную, чтобы подтянуть новый код, если менялись .py файлы."
            )
        return True, "\n".join(lines), restart_scheduled
    except Exception as e:
        return False, "\n".join(lines) + f"\nERROR: {e!s}", False

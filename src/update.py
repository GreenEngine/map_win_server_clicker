"""Self-update helpers for the MCP server (gated by MCP_ALLOW_SELF_UPDATE)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
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
    if not server_py.is_file():
        return

    python_exe = sys.executable
    pid = os.getpid()
    cwd = str(srv)
    log_dir = srv / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    helper_log = log_dir / "mcp_restart_helper.log"

    def _restart() -> None:
        ok_spawn = False
        try:
            # Дать клиенту получить JSON-ответ server_update до выхода процесса.
            time.sleep(2.5)
            env_helper = os.environ.copy()
            env_helper["MCP_RESTART_LOG"] = str(helper_log)
            if sys.platform == "win32":
                cf = int(getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
                cf |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
                cf |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
                if helper.is_file():
                    subprocess.Popen(
                        [python_exe, str(helper), str(pid), python_exe, str(server_py), cwd],
                        cwd=cwd,
                        env=env_helper,
                        creationflags=cf,
                        close_fds=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    ok_spawn = True
                else:
                    # Fallback на случай отсутствия helper: delayed Start-Process.
                    def _sq(v: str) -> str:
                        return v.replace("'", "''")

                    ps_cmd = (
                        "Start-Sleep -Seconds 4; "
                        f"Start-Process -FilePath '{_sq(python_exe)}' "
                        f"-ArgumentList '{_sq(str(server_py))}' "
                        f"-WorkingDirectory '{_sq(cwd)}' -WindowStyle Hidden"
                    )
                    subprocess.Popen(
                        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                        cwd=cwd,
                        creationflags=cf,
                        close_fds=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    ok_spawn = True
            else:
                if not helper.is_file():
                    return
                subprocess.Popen(
                    [python_exe, str(helper), str(pid), python_exe, str(server_py), cwd],
                    cwd=cwd,
                    env=env_helper,
                    start_new_session=True,
                    close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                ok_spawn = True
        except Exception as e:
            try:
                sys.stderr.write(f"mcp_restart_after_update spawn failed: {e!r}\n")
                sys.stderr.flush()
            except Exception:
                pass
        if ok_spawn:
            try:
                os._exit(0)
            except Exception:
                os._exit(1)

    threading.Thread(target=_restart, daemon=True).start()


_self_update_state: dict[str, Any] = {"running": False, "lock": threading.Lock()}


def _self_update_log_path() -> Path:
    return _server_root() / "logs" / "mcp_self_update.log"


def _append_self_update_log(block: str) -> None:
    path = _self_update_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n{ts}\n{block.rstrip()}\n")
    except Exception:
        pass


def _update_sync_requested() -> bool:
    """Старый режим: git/pip блокируют ответ server_update до конца (отладка)."""
    return os.environ.get("MCP_UPDATE_SYNC", "").strip().lower() in ("1", "true", "yes")


def _run_self_update_impl(mode: str = "pip") -> tuple[bool, str, bool]:
    """
    Синхронное обновление (долгий git/pip). Вызывать из фонового потока по умолчанию.
    Returns: (success, log_text, restart_scheduled)
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
                run(cmd, cwd=_server_root())
                lines.append("Скрипт update_server.ps1 выполнен (git/pip). Перезапуск процесса — из Python.")
                if want_ps_restart:
                    schedule_restart_after_update()
                    restart_scheduled = True
                    lines.append(
                        "Перезапуск MCP запланирован (~2.5 с + helper mcp_restart_after_update.py). "
                        "Журнал helper: logs/mcp_restart_helper.log (или MCP_RESTART_LOG); stderr нового процесса: logs/mcp_server_stderr.log."
                    )
                else:
                    lines.append("Перезапустите процесс MCP вручную, чтобы подтянуть новые .py.")
                return True, "\n".join(lines), restart_scheduled
            lines.append(f"Нет скрипта {ps1}, выполняем встроенное обновление…")

        if mode_l in ("git_pull", "full"):
            git_dir = root / ".git"
            if git_dir.exists():
                run(["git", "fetch", "origin"], cwd=root)
                branch_probe = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                branch = (branch_probe.stdout or "").strip() or "main"

                def _has_origin_ref(ref_name: str) -> bool:
                    chk = subprocess.run(
                        ["git", "show-ref", "--verify", f"refs/remotes/origin/{ref_name}"],
                        cwd=str(root),
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    return chk.returncode == 0

                target = branch if _has_origin_ref(branch) else ""
                if not target and _has_origin_ref("main"):
                    target = "main"
                if not target and _has_origin_ref("master"):
                    target = "master"

                if target:
                    run(["git", "pull", "--ff-only", "origin", target], cwd=root)
                else:
                    # Редкий случай нетипичного remote layout.
                    run(["git", "pull", "--ff-only"], cwd=root)
            else:
                lines.append(f"Пропуск git pull: нет {git_dir}")

        if mode_l in ("pip", "full", "git_pull"):
            run([sys.executable, "-m", "pip", "install", "-r", str(req)])

        lines.append("Готово.")
        if _restart_after_update_enabled():
            schedule_restart_after_update()
            restart_scheduled = True
            lines.append(
                "Перезапуск процесса MCP запланирован (через ~2 с). См. logs/mcp_restart_helper.log и logs/mcp_server_stderr.log."
            )
        else:
            lines.append(
                "Перезапустите процесс MCP на Windows вручную, чтобы подтянуть новый код, если менялись .py файлы."
            )
        return True, "\n".join(lines), restart_scheduled
    except Exception as e:
        return False, "\n".join(lines) + f"\nERROR: {e!s}", False


def _self_update_worker(mode: str) -> None:
    try:
        ok, text, rs = _run_self_update_impl(mode)
        _append_self_update_log(f"ok={ok} restart_scheduled={rs}\n{text}")
    except Exception as e:
        _append_self_update_log(f"ok=False restart_scheduled=False\nFATAL: {e!s}")
    finally:
        with _self_update_state["lock"]:
            _self_update_state["running"] = False


def run_self_update(mode: str = "pip") -> tuple[bool, str, bool, bool]:
    """
    Returns:
        (success, log_text, restart_scheduled, update_async)

    По умолчанию (без MCP_UPDATE_SYNC=1): сразу возвращает успех с коротким log,
    реальное git/pip и перезапуск выполняются в фоне — HTTP server_update не висит минутами.
    """
    if os.environ.get("MCP_ALLOW_SELF_UPDATE", "").strip() not in ("1", "true", "True", "yes", "YES"):
        return (
            False,
            "Self-update отключён. Установите MCP_ALLOW_SELF_UPDATE=1 и перезапустите процесс MCP.",
            False,
            False,
        )

    if _update_sync_requested():
        ok, text, rs = _run_self_update_impl(mode)
        return ok, text, rs, False

    with _self_update_state["lock"]:
        if _self_update_state["running"]:
            return (
                False,
                "server_update already running in background; see logs/mcp_self_update.log",
                False,
                False,
            )
        _self_update_state["running"] = True

    threading.Thread(target=_self_update_worker, args=(mode,), daemon=True).start()
    log_path = _self_update_log_path()
    brief = (
        f"Queued background server_update (mode={mode}). "
        f"MCP stays up until git/pip finish; then restart helper runs as before (~2.5s delay). "
        f"Full log: {log_path}. "
        f"Synchronous mode (blocks until done): set MCP_UPDATE_SYNC=1."
    )
    return True, brief, True, True

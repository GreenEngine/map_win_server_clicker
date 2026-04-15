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

# Версия логики self-update (для agent_session / отладки): git для git_pull|full через Python; дефолт режима — full.
_SELF_UPDATE_LOGIC_KEY = "python-git-first-default-full-2026-04-15"


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
        "self_update_logic": _SELF_UPDATE_LOGIC_KEY,
        "summary": f"windows-mcp-server root={srv}; python={sys.version.split()[0]}; git={rev or 'n/a'}",
    }


def _restart_after_update_enabled() -> bool:
    """По умолчанию после успешного обновления планируется перезапуск процесса MCP."""
    v = os.environ.get("MCP_RESTART_AFTER_UPDATE", "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    return True


def _restart_after_update_always() -> bool:
    """Принудительный перезапуск после каждого успешного server_update (старое поведение)."""
    return os.environ.get("MCP_RESTART_AFTER_UPDATE_ALWAYS", "").strip().lower() in ("1", "true", "yes")


def _pip_reported_changes(log_lower: str) -> bool:
    return any(
        s in log_lower
        for s in (
            "successfully installed",
            "installing collected packages",
            "attempting uninstall",
            " upgrading ",
        )
    )


def _git_reported_changes(log_lower: str) -> bool:
    """Признаки того, что git pull реально подтянул коммиты."""
    return any(
        s in log_lower
        for s in (
            "fast-forward",
            " files changed, ",
            " file changed, ",
            "insertions(+)",
            "updating ",
            " merge ",
        )
    )


def _git_reported_already_current(log_lower: str) -> bool:
    return (
        "already up to date" in log_lower
        or "already up-to-date" in log_lower
        or "уже актуальн" in log_lower
    )


def _needs_process_restart_after_update(log_text: str, mode_l: str) -> bool:
    """
    Не дергать os._exit, если git/pip ничего не меняли — меньше простоя и меньше шанс,
    что helper не поднимет новый процесс, пока клиенты ещё держат соединения.

    Принудительно как раньше: MCP_RESTART_AFTER_UPDATE_ALWAYS=1.
    """
    if _restart_after_update_always():
        return True
    t = (log_text or "").lower()
    pip_changed = _pip_reported_changes(t)
    ml = (mode_l or "pip").lower().strip()
    if ml == "pip":
        return pip_changed
    if _git_reported_changes(t):
        return True
    if _git_reported_already_current(t) and not pip_changed:
        return False
    # Непонятный вывод git — безопаснее перезапустить.
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


def _normalize_self_update_mode(mode: str | None) -> tuple[str, str | None]:
    """
    Режимы: pip | git_pull | full.
    Пустой аргумент → full (git fetch + pull --ff-only origin/<ветка> + pip).
    Синонимы полного цикла: git_full, git-full, gitfull, all → full.
    """
    raw = (mode or "").strip().lower()
    if not raw:
        return "full", None
    aliases = {
        "git_full": "full",
        "git-full": "full",
        "gitfull": "full",
        "all": "full",
    }
    out = aliases.get(raw, raw)
    if out in ("pip", "git_pull", "full"):
        return out, None
    return (
        "",
        f"Неизвестный режим server_update: {mode!r}. Допустимо: pip, git_pull, full (синонимы полного git+pip: git_full, all).",
    )


def _git_fetch_pull_ff_only(root: Path, lines: list[str], run) -> None:
    """fetch origin + pull --ff-only на явную ветку origin/<name> (как у удалённого), без слабого голого pull."""
    git_dir = root / ".git"
    if not git_dir.exists():
        lines.append(f"Пропуск git pull: нет {git_dir}")
        return
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
        run(["git", "pull", "--ff-only"], cwd=root)


def _run_self_update_impl(mode: str = "full") -> tuple[bool, str, bool]:
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

    mode_l, mode_err = _normalize_self_update_mode(mode)
    if mode_err:
        return False, mode_err, False
    try:
        use_ps1 = False
        ps1 = _server_root() / "scripts" / "update_server.ps1"
        if sys.platform == "win32" and os.environ.get("MCP_UPDATE_USE_PS1", "").strip().lower() not in (
            "0",
            "false",
            "no",
        ):
            if ps1.is_file():
                use_ps1 = True
            else:
                lines.append(f"Нет скрипта {ps1}, выполняем встроенное обновление…")

        if mode_l in ("git_pull", "full"):
            _git_fetch_pull_ff_only(root, lines, run)

        if use_ps1:
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
                "-RepoRoot",
                str(root),
                "-SkipGit",
            ]
            want_ps_restart = _restart_after_update_enabled()
            run(cmd, cwd=_server_root())
            lines.append(
                "Скрипт update_server.ps1: только pip (venv при наличии); git для режимов git_pull/full "
                "выполняется в Python (git fetch + pull --ff-only origin/<ветка>)."
            )
            joined = "\n".join(lines)
            if want_ps_restart and _needs_process_restart_after_update(joined, mode_l):
                schedule_restart_after_update()
                restart_scheduled = True
                lines.append(
                    "Перезапуск MCP запланирован (~2.5 с + helper mcp_restart_after_update.py). "
                    "Журнал helper: logs/mcp_restart_helper.log (или MCP_RESTART_LOG); stderr нового процесса: logs/mcp_server_stderr.log."
                )
            elif want_ps_restart:
                lines.append(
                    "Перезапуск пропущен: git/pip не сообщили об изменениях (уже актуально). "
                    "Принудительный перезапуск: MCP_RESTART_AFTER_UPDATE_ALWAYS=1."
                )
            else:
                lines.append("Перезапустите процесс MCP вручную, чтобы подтянуть новые .py.")
            return True, "\n".join(lines), restart_scheduled

        if mode_l in ("pip", "full", "git_pull"):
            run([sys.executable, "-m", "pip", "install", "-r", str(req)])

        lines.append("Готово.")
        joined = "\n".join(lines)
        if _restart_after_update_enabled() and _needs_process_restart_after_update(joined, mode_l):
            schedule_restart_after_update()
            restart_scheduled = True
            lines.append(
                "Перезапуск процесса MCP запланирован (через ~2 с). См. logs/mcp_restart_helper.log и logs/mcp_server_stderr.log."
            )
        elif _restart_after_update_enabled():
            lines.append(
                "Перезапуск пропущен: git/pip не сообщили об изменениях. "
                "Принудительно: MCP_RESTART_AFTER_UPDATE_ALWAYS=1."
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


def run_self_update(mode: str | None = "full") -> tuple[bool, str, bool, bool]:
    """
    Returns:
        (success, log_text, restart_scheduled, update_async)

    Режим по умолчанию: **full** (git fetch + pull --ff-only origin/<ветка> + pip). Только pip: mode=pip.

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

    mode_n, mode_err = _normalize_self_update_mode(mode)
    if mode_err:
        return False, mode_err, False, False

    if _update_sync_requested():
        ok, text, rs = _run_self_update_impl(mode_n)
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

    threading.Thread(target=_self_update_worker, args=(mode_n,), daemon=True).start()
    log_path = _self_update_log_path()
    brief = (
        f"Queued background server_update (mode={mode_n}). "
        f"MCP stays up during git/pip; process restarts only if git/pip reported changes "
        f"(else no os._exit; force always: MCP_RESTART_AFTER_UPDATE_ALWAYS=1). "
        f"Full log: {log_path}. "
        f"Blocking mode: MCP_UPDATE_SYNC=1."
    )
    return True, brief, False, True

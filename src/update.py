"""Self-update helpers for the MCP server (gated by MCP_ALLOW_SELF_UPDATE)."""

from __future__ import annotations

import os
import subprocess
import sys
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


def run_self_update(mode: str = "pip") -> tuple[bool, str]:
    """
    Returns:
        (success, log_text)
    """
    if os.environ.get("MCP_ALLOW_SELF_UPDATE", "").strip() not in ("1", "true", "True", "yes", "YES"):
        return (
            False,
            "Self-update отключён. Установите MCP_ALLOW_SELF_UPDATE=1 и перезапустите процесс MCP.",
        )

    root = _repo_root()
    srv = _server_root()
    req = srv / "requirements.txt"
    if not req.is_file():
        return False, f"Не найден {req}"

    lines: list[str] = []

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
            and os.environ.get("MCP_UPDATE_USE_PS1", "").strip() in ("1", "true", "yes", "YES")
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
                run(cmd, cwd=_server_root())
                lines.append(
                    "Скрипт update_server.ps1 выполнен. Перезапустите процесс MCP, чтобы подтянуть новые .py."
                )
                return True, "\n".join(lines)
            lines.append(f"Нет скрипта {ps1}, выполняем встроенное обновление…")

        if mode_l in ("git_pull", "full"):
            git_dir = root / ".git"
            if git_dir.exists():
                run(["git", "pull", "--ff-only"], cwd=root)
            else:
                lines.append(f"Пропуск git pull: нет {git_dir}")

        if mode_l in ("pip", "full", "git_pull"):
            run([sys.executable, "-m", "pip", "install", "-r", str(req)])

        lines.append(
            "Готово. Перезапустите процесс MCP на Windows, чтобы подтянуть новый код, если менялись .py файлы."
        )
        return True, "\n".join(lines)
    except Exception as e:
        return False, "\n".join(lines) + f"\nERROR: {e!s}"

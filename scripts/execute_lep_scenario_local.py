#!/usr/bin/env python3
"""
Локальное выполнение JSON-сценария LEP **на той же Windows-машине**, где установлен код
`windows-mcp-server` (тот же venv, что и у MCP). Вызывает Python-функции инструментов из
`src/server.py` напрямую — **без HTTP** и **без Cursor**.

  cd D:\\path\\to\\LEP\\windows-mcp-server
  .\\.venv\\Scripts\\activate
  set PYTHONPATH=.
  python scripts/execute_lep_scenario_local.py --scenario scenarios/_template.json

Проверка JSON без импорта server (macOS/Linux):

  PYTHONPATH=. python scripts/execute_lep_scenario_local.py --scenario scenarios/_template.json --validate-only

Логика шагов: `src/lep_scenario_runner.py` (тот же контракт, что у MCP-инструмента `lep_run_scenario`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = MCP_ROOT / "scenarios"


def resolve_scenario(arg: str) -> Path:
    raw = Path(arg)
    if raw.is_file():
        return raw.resolve()
    base = SCENARIOS_DIR / arg
    if base.is_file():
        return base.resolve()
    if (base.with_suffix(".json")).is_file():
        return base.with_suffix(".json").resolve()
    print(f"Сценарий не найден: {arg} (искали в {SCENARIOS_DIR})", file=sys.stderr)
    raise SystemExit(1)


def _setup_path() -> None:
    root = str(MCP_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Выполнить JSON-сценарий LEP локально (Windows) или только проверить (--validate-only)"
    )
    ap.add_argument("--scenario", type=str, required=True, help="Путь к .json или имя в scenarios/")
    ap.add_argument("--validate-only", action="store_true", help="Только проверить JSON (без импорта server)")
    ap.add_argument("--dry-run", action="store_true", help="Печать шагов без вызова (только Windows)")
    args = ap.parse_args()

    _setup_path()
    from src import lep_scenario_runner as lsr  # noqa: E402

    path = resolve_scenario(args.scenario)
    data = lsr.load_scenario_dict(path)
    try:
        lsr.validate_scenario(data, path)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.validate_only:
        print(f"OK validate-only: {path}", file=sys.stderr)
        return 0

    if sys.platform != "win32":
        print(
            "Локальное выполнение UIA только на Windows. Используйте --validate-only или MCP lep_run_scenario на ВМ.",
            file=sys.stderr,
        )
        return 2

    import src.server as server  # noqa: E402

    for inv in sorted({s["invoke"] for s in data["steps"] if isinstance(s, dict) and "invoke" in s}):
        if not hasattr(server, inv):
            print(f"ERR: на сервере нет функции инструмента «{inv}»", file=sys.stderr)
            return 1

    def _get_tool(name: str):
        return getattr(server, name)

    if args.dry_run:
        for i, step in enumerate(data["steps"], start=1):
            print(f"[dry-run] {i} {step.get('invoke')} args={step.get('args')!r}", file=sys.stderr)
        return 0

    prefix = str(data.get("id", "scenario"))[:40]
    ok, log = lsr.run_scenario_json(data, get_tool=_get_tool, id_prefix=prefix)
    for row in log:
        print(f"step {row.get('n')} {row.get('invoke')} ok={row.get('ok')} code={row.get('code')}", file=sys.stderr)
    if not ok:
        print(log[-1].get("raw_excerpt", ""), file=sys.stderr)
        return 1
    print(f"OK scenario completed: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

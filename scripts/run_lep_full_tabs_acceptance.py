#!/usr/bin/env python3
"""
Приёмка LEP в nanoCAD: smoke MCP + полный обход главных вкладок палитры (UIA).

Один вызов на стороне ВМ (без пошагового агента в Cursor):
  MCP tool **lep_run_scenario_sequence** с
  scenario_names_csv = smoke + полный палитровый сценарий (см. DEFAULT_SEQUENCE ниже).

Сценарии и id вкладок: ../scenarios/*.json, эталон **ALL/Docs/QA_UiaIds.md** (в корне LEP).

Примеры:
  python scripts/run_lep_full_tabs_acceptance.py --validate
  python scripts/run_lep_full_tabs_acceptance.py --print-mcp-hint
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = MCP_ROOT / "scenarios"
REPO_LEP_ROOT = MCP_ROOT.parent  # каталог LEP (родитель windows-mcp-server/)
QA_IDS = REPO_LEP_ROOT / "ALL" / "Docs" / "QA_UiaIds.md"

# Совпадает с дефолтом lep_run_scenario_sequence в server.py (smoke + все вкладки).
DEFAULT_SEQUENCE = (
    "lep_mcp_full_operability_smoke.json,"
    "lep_plugin_full_palette_uia.json"
)


def _validate_one(name: str) -> Path:
    p = SCENARIOS_DIR / name
    if not p.is_file():
        print(f"Нет файла: {p}", file=sys.stderr)
        sys.exit(1)
    if str(MCP_ROOT) not in sys.path:
        sys.path.insert(0, str(MCP_ROOT))
    from src import lep_scenario_runner as lsr

    import json

    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    lsr.validate_scenario(data, p)
    return p


def cmd_validate() -> int:
    _validate_one("lep_mcp_full_operability_smoke.json")
    _validate_one("lep_plugin_full_palette_uia.json")
    print("OK: оба JSON-сценария валидны.", file=sys.stderr)
    return 0


def cmd_print_mcp_hint() -> int:
    qa = QA_IDS.resolve()
    qa_note = f"Стабильные automation_id: {qa}" if qa.is_file() else "Стабильные automation_id: ALL/Docs/QA_UiaIds.md (путь от корня LEP)"
    csv = DEFAULT_SEQUENCE.replace("\n", "")
    print(
        f"""## Один вызов MCP (Windows)

Инструмент: **`lep_run_scenario_sequence`**
Аргументы (пример):
- **`scenario_names_csv`**: `{csv}`

Ожидаемый результат: **`data.all_scenarios_ok`** и журналы в **`data.runs[]`**.
Перед прогоном при необходимости: **`health`** → **`agent_session`**, переменные **`MCP_LEP_OPEN_DWG`** / **`LEP_GOLDEN_DWG`** — см. **docs/DEPLOY_VM_CHECKLIST.md**.

{qa_note}
"""
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="LEP: smoke + все вкладки палитры — валидация JSON и подсказка MCP")
    ap.add_argument("--validate", action="store_true", help="Проверить оба сценария через lep_scenario_runner")
    ap.add_argument(
        "--print-mcp-hint",
        action="store_true",
        help="Вывести markdown: один вызов lep_run_scenario_sequence",
    )
    args = ap.parse_args()
    if args.validate:
        return cmd_validate()
    if args.print_mcp_hint:
        return cmd_print_mcp_hint()
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

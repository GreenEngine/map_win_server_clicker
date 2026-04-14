#!/usr/bin/env python3
"""
Повторяемый прогон матрицы QA LEP (10× и т.д.): печать чеклиста для агента Cursor
или развёртывание шагов с новыми client_request_id.

Использование:
  python scripts/run_lep_qa_matrix.py --runs 10 --matrix ../../reports/qa_full_plugin_10runs_matrix.json

Переменные:
  LEP_GOLDEN_DWG — если задана, в начало чеклиста добавляется напоминание открыть этот DWG.

Прямой вызов MCP по HTTP здесь намеренно не реализован: транспорт FastMCP streamable-http
требует клиент MCP; для автоматизации используйте инструменты из Cursor или обёртку на стороне ВМ.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def load_matrix(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def expand_template(steps: list[dict], run_id: int, prefix: str) -> list[dict]:
    out: list[dict] = []
    for step in steps:
        s = dict(step)
        rid = f"{prefix}-r{run_id}-n{step.get('n', len(out) + 1)}-{uuid.uuid4().hex[:8]}"
        s["client_request_id"] = rid
        out.append(s)
    return out


def format_checklist(run_id: int, steps: list[dict]) -> str:
    lines = [f"## Прогон {run_id}", ""]
    golden = (os.environ.get("LEP_GOLDEN_DWG") or "").strip()
    if golden:
        lines.append(f"- Перед сценарием открыть золотой чертёж: `{golden}`")
        lines.append("")
    for s in steps:
        n = s.get("n", "?")
        rid = s.get("client_request_id", "")
        if "tools" in s:
            lines.append(f"{n}. Вызвать: **{', '.join(s['tools'])}** — `client_request_id`: `{rid}`")
            if s.get("args"):
                lines.append(f"   - args: `{json.dumps(s['args'], ensure_ascii=False)}`")
        elif s.get("action") == "uia_click":
            lines.append(
                f"{n}. **uia_click** name=`{s.get('name')}` control_type=`{s.get('control_type')}` "
                f"nth={s.get('nth', 0)} — `{rid}`"
            )
        elif s.get("action") == "modal":
            lines.append(f"{n}. **uia_modal_ok** (при необходимости titlebar_close / mouse) — `{rid}`")
        else:
            lines.append(f"{n}. {json.dumps(s, ensure_ascii=False)} — `{rid}`")
        exp = s.get("expect")
        if exp:
            lines.append(f"   - ожидание: {exp}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="LEP QA matrix → чеклист / JSON шагов")
    ap.add_argument("--matrix", type=Path, default=Path("reports/qa_full_plugin_10runs_matrix.json"))
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--prefix", type=str, default="full10")
    ap.add_argument("--out-md", type=Path, default=None, help="Путь для Markdown чеклиста")
    ap.add_argument("--out-json", type=Path, default=None, help="Путь для JSON со всеми прогонами")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    matrix_path = args.matrix if args.matrix.is_absolute() else root / args.matrix
    if not matrix_path.is_file():
        print(f"Matrix not found: {matrix_path}", file=sys.stderr)
        return 1

    data = load_matrix(matrix_path)
    template = data.get("steps_template") or []
    if not template:
        print("steps_template empty", file=sys.stderr)
        return 1

    all_runs: list[dict] = []
    md_chunks: list[str] = []
    md_chunks.append(f"# LEP QA matrix ({args.runs} прогонов)")
    md_chunks.append("")
    md_chunks.append(f"- Источник: `{matrix_path}`")
    md_chunks.append(f"- Сгенерировано: {datetime.now(timezone.utc).isoformat()}")
    md_chunks.append("")
    md_chunks.append("Рекомендация: для дерева палитры использовать **`uia_list_subtree`** (`process_name=nCAD.exe`).")
    md_chunks.append("")

    for r in range(1, args.runs + 1):
        steps = expand_template(template, r, args.prefix)
        all_runs.append({"run_id": r, "steps": steps})
        md_chunks.append(format_checklist(r, steps))

    md_text = "\n".join(md_chunks)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(md_text, encoding="utf-8")
        print(f"Wrote {args.out_md}")
    else:
        print(md_text)

    if args.out_json:
        payload = {
            "source_matrix": str(matrix_path),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "runs": all_runs,
        }
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {args.out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

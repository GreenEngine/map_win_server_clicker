#!/usr/bin/env python3
"""
Генерация одного markdown-промпта для агента lep-plugin-tester по JSON-сценарию.

  python scripts/run_lep_scenario.py --scenario _template.json
  python scripts/run_lep_scenario.py --name lep_feature_template   # scenarios/lep_feature_template.json

Сценарии: ../scenarios/*.json — см. ../scenarios/README.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = MCP_ROOT / "scenarios"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from src.lep_scenario_runner import ALLOWED_INVOKES  # noqa: E402


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
    sys.exit(1)


def load_scenario(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print("Корень JSON должен быть объектом", file=sys.stderr)
        sys.exit(1)
    return data


def validate_scenario(data: dict, path: Path) -> None:
    from src import lep_scenario_runner as lsr

    try:
        lsr.validate_scenario(data, path)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def build_markdown_prompt(scenario_path: Path, data: dict) -> str:
    sid = str(data["id"])
    title = str(data["title"])
    skip_prep = bool(data.get("skip_nanocad_lep_prepare"))
    steps_json = json.dumps(data.get("steps", []), ensure_ascii=False, indent=2)
    abs_path = scenario_path.resolve()

    prep_block = (
        "**Подготовка CAD:** в сценарии `skip_nanocad_lep_prepare: true` — не вызывай `nanocad_lep_prepare`; убедись вручную, что nCAD и палитра в нужном состоянии."
        if skip_prep
        else (
            "**Подготовка CAD:** если в `steps` есть `nanocad_lep_prepare` — выполни как в JSON; если нет — один раз вызови `nanocad_lep_prepare` с умолчаниями до первого UI-действия, если палитра могла быть не поднята."
        )
    )

    return f"""## Задача: прогон JSON-сценария LEP / nanoCAD

Ты **lep-plugin-tester**. Используй только MCP **Windows** (например **user-lep-windows** / тот, что настроен в Cursor).

### Исходные данные

- **Файл сценария (абсолютный путь):** `{abs_path}`
- **id:** `{sid}`
- **title:** {title}

Открой файл, прочитай JSON. Массив **`steps`** выполняй **строго по порядку**: для каждого элемента вызови инструмент MCP **`invoke`** с аргументами **`args`** (если `args` нет — вызывай только с `client_request_id` по желанию).

Встроенные шаги (для справки, дублируй из файла при выполнении):

```json
{steps_json}
```

### Обязательный порядок и правила

1. Сначала **`health`**, затем **`agent_session`** (если их нет в `steps` — выполни до остальных шагов).
2. {prep_block}
3. Выполняй элементы **`steps`** по порядку: `invoke` + `args`.
4. После **каждого** шага, меняющего UI (`uia_click`, `send_keys`, модалки и т.п.), если в JSON **сразу** не следуют два шага `capture_window` и `capture_monitor` — добавь пару снимков сам (политика lep-plugin-tester). Для имён файлов:
   - полный **`out_path`** на диске Windows, **или**
   - **`filename_suffix`** в аргументах `capture_*` (сервер сохранит в **`MCP_CAPTURE_DIR`** или temp).
   - Рекомендуемый смысл `filename_suffix`: `{sid}_<n>_<краткий_контекст>_win` / `_mon` (латиница, цифры, `_`, `-`).
5. Для шагов `capture_*` из JSON сверяй картинку с полем **`expect`** (если есть).
6. Не ставь PASS только из `ok:true` в ответе MCP; **итог шага** — по скринам и `expect`.
7. Итоговый отчёт — по формату из `.cursor/agents/lep-plugin-tester.md` (таблица шагов, пути **`data.path`** к PNG).

### Напоминание

- Вкладка **Настройки** в палитре LEP: при клике по имени часто **`nth=1`**.
- Стабильные id: `ALL/Docs/QA_UiaIds.md`.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="LEP MCP JSON-сценарий → промпт для чата")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scenario", type=str, help="Путь к .json или имя файла в scenarios/")
    g.add_argument("--name", type=str, help="Имя без пути: scenarios/<name>.json")
    ap.add_argument("--out-md", type=Path, default=None, help="Сохранить промпт в файл")
    args = ap.parse_args()

    raw = args.scenario or args.name
    path = resolve_scenario(raw)
    data = load_scenario(path)
    validate_scenario(data, path)
    md = build_markdown_prompt(path, data)
    if args.out_md:
        args.out_md = args.out_md.resolve()
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(md, encoding="utf-8")
        print(f"Wrote {args.out_md}", file=sys.stderr)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

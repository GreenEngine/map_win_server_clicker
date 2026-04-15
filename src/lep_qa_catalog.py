"""
Каталог сценариев и подсказки для полного QA плагина LEP (nanoCAD) через MCP.
Не вызывает UIA — безопасно на любой платформе при импорте.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _server_package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_scenarios_dir() -> Path:
    """Каталог JSON-сценариев: MCP_REPO_ROOT (монорепо LEP) или рядом с сервером."""
    env = (os.environ.get("MCP_REPO_ROOT") or "").strip()
    candidates: list[Path] = []
    if env:
        er = Path(env)
        candidates.append(er / "windows-mcp-server" / "scenarios")
        candidates.append(er / "scenarios")
    candidates.append(_server_package_root() / "scenarios")
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[-1]


def resolve_reports_dir() -> Path | None:
    env = (os.environ.get("MCP_REPO_ROOT") or "").strip()
    if env:
        for sub in ("reports", "windows-mcp-server/reports"):
            p = Path(env) / sub
            if p.is_dir():
                return p
    r = _server_package_root() / "reports"
    return r if r.is_dir() else None


def list_scenario_files(scenarios_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not scenarios_dir.is_dir():
        return out
    for path in sorted(scenarios_dir.glob("*.json")):
        name = path.name
        meta: dict[str, Any] = {
            "name": name,
            "path": str(path.resolve()),
            "relative": f"scenarios/{name}",
        }
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                meta["title"] = data.get("title") or data.get("name")
                steps = data.get("steps")
                if isinstance(steps, list):
                    meta["steps_count"] = len(steps)
        except Exception as exc:  # noqa: BLE001 — каталог для агента
            meta["parse_error"] = str(exc)[:200]
        out.append(meta)
    return out


def lep_qa_catalog_payload() -> dict[str, Any]:
    """
    Сводка для агента: где сценарии, какие файлы, стандартный порядок инструментов для полного теста LEP.
    """
    scenarios_dir = resolve_scenarios_dir()
    reports = resolve_reports_dir()
    matrix_candidates = []
    if reports:
        for fname in ("qa_full_plugin_10runs_matrix.json",):
            p = reports / fname
            if p.is_file():
                matrix_candidates.append(str(p.resolve()))
    return {
        "scenarios_dir": str(scenarios_dir.resolve()),
        "scenarios": list_scenario_files(scenarios_dir),
        "qa_matrix_paths_hint": matrix_candidates,
        "run_scenario_cli": "python windows-mcp-server/scripts/run_lep_scenario.py --scenario <path>  (из корня монорепо LEP)",
        "execute_scenario_local_cli": "cd windows-mcp-server && .venv\\Scripts\\activate && set PYTHONPATH=. && python scripts/execute_lep_scenario_local.py --scenario scenarios/<file>.json",
        "execute_scenario_validate_only": "PYTHONPATH=. python scripts/execute_lep_scenario_local.py --scenario scenarios/_template.json --validate-only",
        "run_matrix_cli": "python windows-mcp-server/scripts/run_lep_qa_matrix.py --matrix <path> --runs 10",
        "docs_repo_relative": [
            "windows-mcp-server/README.md",
            "windows-mcp-server/docs/DEPLOY_VM_CHECKLIST.md",
            "windows-mcp-server/scenarios/README.md",
            "ALL/Docs/QA_UiaIds.md",
        ],
        "mcp_tool_order_full_lep_smoke": [
            "health",
            "agent_session",
            "lep_qa_catalog",
            "lep_run_scenario",
            "nanocad_lep_prepare",
            "capture_window",
            "capture_monitor",
            "uia_list_subtree",
            "uia_click",
            "capture_window",
            "capture_monitor",
            "uia_modal_ok",
        ],
        "note": "Полный приёмочный прогон = подготовка nanoCAD + пара capture после каждого изменения UI + uia_list_subtree; см. agent_session.workflow",
        "primary_acceptance_scenario": "lep_mcp_full_operability_smoke.json",
        "primary_acceptance_lep_run_scenario": 'lep_run_scenario("lep_mcp_full_operability_smoke.json") на ВМ — один MCP-вызов для критериев product-delivery A–E',
        "orchestrator_product_delivery": {
            "repo_track": "pytest/diff в репозитории — не заменяет UI на ВМ.",
            "windows_track": "Каждый приёмочный прогон nanoCAD через MCP считать отдельным шагом; вести windows_run_index..windows_run_max (по умолчанию 30 в product-delivery; см. .cursor/skills/product-delivery/SKILL.md).",
            "autonomy_goal": "Автономность = закрытие сценариев без ручных кликов в CAD (кроме блокеров: NETLOAD, RDP без framebuffer).",
            "autonomous_batch": "На ВМ: (1) MCP lep_run_scenario(scenario_name) — один вызов, весь JSON; (2) execute_lep_scenario_local.py — то же локально в venv; Планировщик заданий в пользовательской сессии.",
            "mcp_self_heal_on_connected_server": "Подключённый MCP: при расхождении uia_tools_revision с репо или при подозрении на старый server.py — server_update(git_pull|full) при MCP_ALLOW_SELF_UPDATE=1 и MCP_REPO_ROOT; после data.restart_scheduled — пауза, health, agent_session, затем повтор UI-прогона. Иначе ручной деплой (DEPLOY_VM_CHECKLIST).",
        },
    }

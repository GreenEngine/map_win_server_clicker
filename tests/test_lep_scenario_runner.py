"""lep_scenario_runner: валидация и resolve без Windows."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import lep_scenario_runner as lsr


def test_validate_template_json() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "scenarios" / "_template.json"
    data = lsr.load_scenario_dict(path)
    lsr.validate_scenario(data, path)


def test_validate_full_operability_smoke_json() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "scenarios" / "lep_mcp_full_operability_smoke.json"
    data = lsr.load_scenario_dict(path)
    lsr.validate_scenario(data, path)


def test_validate_full_palette_uia_json() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "scenarios" / "lep_plugin_full_palette_uia.json"
    data = lsr.load_scenario_dict(path)
    assert data.get("stop_on_first_error") is False
    lsr.validate_scenario(data, path)


def test_resolve_under_root() -> None:
    root = Path(__file__).resolve().parent.parent / "scenarios"
    p = lsr.resolve_scenario_path_under_root("_template.json", root)
    assert p.name == "_template.json"


def test_resolve_rejects_traversal() -> None:
    root = Path(__file__).resolve().parent.parent / "scenarios"
    with pytest.raises(ValueError, match="Недопустимое"):
        lsr.resolve_scenario_path_under_root("../secrets.json", root)

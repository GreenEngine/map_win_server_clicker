"""execute_lep_scenario_local.py --validate-only не импортирует src.server."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_validate_only_template_json() -> None:
    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "execute_lep_scenario_local.py"
    r = subprocess.run(
        [sys.executable, str(script), "--scenario", "scenarios/_template.json", "--validate-only"],
        cwd=str(root),
        env={**dict(__import__("os").environ), "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr + r.stdout

"""Согласованность agent_session, каталога QA и имён инструментов FastMCP в server.py."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from src import lep_qa_catalog
from src import session
from src.protocol import PROTOCOL_VERSION


def _server_py_path() -> Path:
    return Path(__file__).resolve().parent.parent / "src" / "server.py"


def _mcp_tool_function_names_via_ast(server_py: Path) -> set[str]:
    tree = ast.parse(server_py.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if _is_mcp_tool_decorator(dec):
                out.add(node.name)
                break
    return out


def _is_mcp_tool_decorator(dec: ast.expr) -> bool:
    """True для @mcp.tool и @mcp.tool(...)."""
    func = dec
    if isinstance(dec, ast.Call):
        func = dec.func
    if isinstance(func, ast.Attribute) and func.attr == "tool":
        if isinstance(func.value, ast.Name) and func.value.id == "mcp":
            return True
    return False


def _mcp_tool_function_names_via_regex(server_py: Path) -> set[str]:
    """Имена функций сразу после цепочки @mcp.tool() и опциональных декораторов."""
    text = server_py.read_text(encoding="utf-8")
    pat = re.compile(
        r"@mcp\.tool\(\)\s*(?:\n\s*@[^\n]+)*\n\s*def\s+(\w+)\s*\(",
        re.MULTILINE,
    )
    return set(pat.findall(text))


def test_agent_session_payload_protocol_and_tools() -> None:
    payload = session.agent_session_payload()
    assert payload["protocol_version"] == PROTOCOL_VERSION
    tools = payload["tools"]
    assert isinstance(tools, list)
    assert len(tools) > 0
    for t in tools:
        assert isinstance(t, dict)
        assert "name" in t and isinstance(t["name"], str)


def test_lep_qa_catalog_payload_shape() -> None:
    data = lep_qa_catalog.lep_qa_catalog_payload()
    assert "scenarios_dir" in data
    assert isinstance(data["scenarios_dir"], str)
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    order = data["mcp_tool_order_full_lep_smoke"]
    assert isinstance(order, list)
    assert "lep_qa_catalog" in order
    orch = data["orchestrator_product_delivery"]
    assert isinstance(orch, dict)
    assert set(orch.keys()) >= {"repo_track", "windows_track", "autonomy_goal", "autonomous_batch"}
    assert "mcp" in orch["windows_track"].lower()


def test_session_tool_names_match_server_mcp_tools() -> None:
    server_py = _server_py_path()
    from_ast = _mcp_tool_function_names_via_ast(server_py)
    from_rx = _mcp_tool_function_names_via_regex(server_py)
    assert from_ast == from_rx, "AST и regex должны давать один набор имён @mcp.tool"
    assert "lep_qa_catalog" in from_ast

    session_names = {t["name"] for t in session.agent_session_payload()["tools"]}
    assert session_names == from_ast

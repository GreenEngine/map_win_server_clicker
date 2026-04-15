"""Логика _click_uia_target без pywinauto (моки)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.uia_tools import _click_uia_target, _pick_largest_mainlike_window


class _Rect:
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


def test_click_input_when_rect_large_enough() -> None:
    t = MagicMock()
    t.rectangle.return_value = _Rect(0, 0, 100, 40)
    strategy, meta = _click_uia_target(t)
    assert strategy == "click_input"
    assert meta["rect_width"] == 100
    assert meta["rect_height"] == 40
    t.click_input.assert_called_once()
    t.select.assert_not_called()
    t.invoke.assert_not_called()


def test_select_when_rect_degenerate() -> None:
    t = MagicMock()
    t.rectangle.return_value = _Rect(10, 20, 10, 20)  # w=0, h=0
    t.select = MagicMock()
    strategy, meta = _click_uia_target(t)
    assert strategy == "pattern_select"
    t.select.assert_called_once()
    t.click_input.assert_not_called()


def test_invoke_when_select_missing() -> None:
    t = MagicMock(spec=["rectangle", "invoke", "click_input"])
    t.rectangle.return_value = _Rect(0, 0, 0, 0)
    t.invoke = MagicMock()
    strategy, meta = _click_uia_target(t)
    assert strategy == "pattern_invoke"
    t.invoke.assert_called_once()


def test_pick_largest_mainlike_prefers_nanocad_title() -> None:
    app = MagicMock()
    w_ps = MagicMock()
    w_ps.is_visible.return_value = True
    w_ps.window_text.return_value = "Windows PowerShell"
    w_ps.rectangle.return_value = _Rect(0, 0, 900, 700)
    w_nc = MagicMock()
    w_nc.is_visible.return_value = True
    w_nc.window_text.return_value = "Plan.dwg - nanoCAD"
    w_nc.rectangle.return_value = _Rect(0, 0, 800, 600)
    app.windows.return_value = [w_ps, w_nc]
    best = _pick_largest_mainlike_window(app)
    assert best is w_nc


def test_raises_when_no_pattern_and_rect_bad() -> None:
    t = MagicMock(spec=["rectangle", "click_input"])
    t.rectangle.return_value = _Rect(5, 5, 5, 5)
    t.click_input.side_effect = RuntimeError("fail")
    with pytest.raises(RuntimeError, match="прямоугольник"):
        _click_uia_target(t)

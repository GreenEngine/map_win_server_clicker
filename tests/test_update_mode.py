"""Нормализация режима server_update."""

from __future__ import annotations

from src.update import _normalize_self_update_mode


def test_default_full_empty_and_whitespace() -> None:
    assert _normalize_self_update_mode("") == ("full", None)
    assert _normalize_self_update_mode("   ") == ("full", None)
    assert _normalize_self_update_mode(None) == ("full", None)


def test_aliases_to_full() -> None:
    for raw in ("git_full", "GIT_FULL", "git-full", "gitfull", "all"):
        assert _normalize_self_update_mode(raw) == ("full", None)


def test_pip_git_pull_full() -> None:
    assert _normalize_self_update_mode("pip") == ("pip", None)
    assert _normalize_self_update_mode("GIT_PULL") == ("git_pull", None)
    assert _normalize_self_update_mode("full") == ("full", None)


def test_unknown_mode_error() -> None:
    out, err = _normalize_self_update_mode("typo_mode")
    assert out == ""
    assert err is not None
    assert "typo_mode" in err

"""
Типовая последовательность для nanoCAD + LEP: проверка процесса, запуск, снятие модалок, команда LEP, ожидание палитры.

Используется инструментом MCP `nanocad_lep_prepare` и не дублирует низкоуровневую логику — только вызывает `uia_tools`.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from typing import Any

from src import uia_tools
from src.protocol import err_json, ok_json, parse_request_id

PROCESS_NCAD = "nCAD.exe"
CMDLINE_AUTOMATION_ID = "1011"
PALETTE_ANCHOR_ID = "lep_palette_root"


def _loads(s: str) -> dict[str, Any]:
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def nanocad_uia_connected(timeout_sec: float = 2.0) -> bool:
    """True, если к nCAD.exe уже можно подключиться через UIA (процесс жив)."""
    if sys.platform != "win32":
        return False
    try:
        from pywinauto import Application

        Application(backend="uia").connect(path=PROCESS_NCAD, timeout=max(0.5, float(timeout_sec)))
        return True
    except Exception:
        return False


def _append_step(steps: list[dict[str, Any]], name: str, payload: dict[str, Any]) -> None:
    steps.append({"step": name, "ts": time.time(), **payload})


def nanocad_lep_prepare(
    *,
    skip_launch_if_running: bool = True,
    launch_arguments: str = "",
    open_dwg_path: str | None = None,
    launch_wait_timeout_sec: float = 90.0,
    modal_rounds: int = 14,
    modal_timeout_sec: float = 3.5,
    modal_button_titles: str = "OK,ОК,Закрыть,Close,Cancel,Отмена,Пропустить,Skip",
    after_modal_titlebar_rounds: int = 2,
    lep_command: str | None = None,
    wait_palette_timeout_sec: float = 55.0,
    wait_palette_poll_sec: float = 0.45,
    client_request_id: str | None = None,
) -> str:
    """
    Идемпотентная подготовка: при необходимости запуск nCAD, закрытие типовых модалок,
    фокус командной строки (automation_id 1011), ввод команды LEP (+ Enter), ожидание lep_palette_root.

    lep_command: по умолчанию из MCP_LEP_COMMAND или «LEP».
    open_dwg_path: путь к .dwg — подставляется в аргументы запуска nCAD.exe (только при этом запуске процесса);
        если не задан — используется MCP_LEP_OPEN_DWG из окружения. Имеет смысл для автономного открытия «золотого» чертежа при холодном старте.
    """
    rid = parse_request_id(client_request_id)
    if sys.platform != "win32":
        return err_json("ERR_PLATFORM", "nanocad_lep_prepare только на Windows", request_id=rid)

    steps: list[dict[str, Any]] = []
    cmd = (lep_command or os.environ.get("MCP_LEP_COMMAND") or "LEP").strip()
    if not cmd:
        return err_json("ERR_VALIDATION", "lep_command пустой", request_id=rid)

    dwg = (open_dwg_path or os.environ.get("MCP_LEP_OPEN_DWG") or os.environ.get("LEP_GOLDEN_DWG") or "").strip()
    launch_args_effective = (launch_arguments or "").strip()
    if dwg:
        if not os.path.isfile(dwg):
            return err_json(
                "ERR_VALIDATION",
                f"open_dwg_path / MCP_LEP_OPEN_DWG / LEP_GOLDEN_DWG: файл не найден: {dwg!r}",
                request_id=rid,
            )
        quoted = shlex.quote(dwg)
        launch_args_effective = f"{launch_args_effective} {quoted}".strip()

    running = nanocad_uia_connected(2.0)
    _append_step(steps, "check_uia_connected", {"running": running})

    need_launch = (not running) or (not skip_launch_if_running)
    if need_launch:
        lp = _loads(
            uia_tools.launch_process(
                "AUTO_NANOCAD",
                launch_args_effective,
                launch_wait_timeout_sec,
                client_request_id=rid,
            )
        )
        _append_step(
            steps,
            "launch_process",
            {
                "ok": lp.get("ok"),
                "code": lp.get("code"),
                "data": lp.get("data"),
                "forced": bool(running and not skip_launch_if_running),
                "launch_arguments_effective": launch_args_effective or None,
                "open_dwg_path": dwg or None,
            },
        )
        if not lp.get("ok"):
            return err_json(
                str(lp.get("code") or "ERR_UIA"),
                str(lp.get("message") or "launch_process failed"),
                data={"steps": steps, "launch": lp.get("data")},
                request_id=rid,
            )
        time.sleep(1.0)
    else:
        _append_step(
            steps,
            "launch_skipped",
            {
                "reason": "nCAD.exe already in UIA (skip_launch_if_running=true)",
                "open_dwg_note": (
                    "DWG не передан в запуск: при уже запущенном nCAD откройте чертёж вручную или перезапустите с skip_launch_if_running=false и open_dwg_path"
                    if dwg
                    else None
                ),
            },
        )

    # Снять модалки кнопками (несколько подряд — «Совет дня», лицензия, предупреждения).
    for i in range(max(1, int(modal_rounds))):
        body = _loads(
            uia_tools.uia_modal_ok(
                title_regex=None,
                button_titles=modal_button_titles,
                timeout_sec=float(modal_timeout_sec),
                owner_process_name=PROCESS_NCAD,
                client_request_id=rid,
            )
        )
        if body.get("ok"):
            _append_step(steps, "uia_modal_ok", {"round": i, "data": body.get("data")})
            time.sleep(0.35)
            continue
        if body.get("code") == "ERR_NOT_FOUND":
            _append_step(steps, "uia_modal_ok_done", {"round": i, "note": "no matching modal"})
            break
        _append_step(steps, "uia_modal_ok_error", {"round": i, "response": body})
        break

    # Доп. проход: мелкие окна вроде «Совет дня» — крестик в заголовке.
    for j in range(max(0, int(after_modal_titlebar_rounds))):
        tb = _loads(
            uia_tools.uia_modal_titlebar_close(
                title_regex=r"Совет|Tip|nanoCAD|день",
                timeout_sec=float(modal_timeout_sec),
                client_request_id=rid,
            )
        )
        if tb.get("ok"):
            _append_step(steps, "uia_modal_titlebar_close", {"round": j, "data": tb.get("data")})
            time.sleep(0.35)
        else:
            _append_step(steps, "uia_modal_titlebar_close_skip", {"round": j, "code": tb.get("code")})
            break

    # Палитра уже есть — не шлём команду повторно без необходимости.
    probe = _loads(
        uia_tools.wait_for(
            process_name=PROCESS_NCAD,
            title_contains=None,
            automation_id=PALETTE_ANCHOR_ID,
            name=None,
            timeout_sec=min(2.5, float(wait_palette_timeout_sec)),
            poll_sec=wait_palette_poll_sec,
            client_request_id=rid,
        )
    )
    if probe.get("ok"):
        _append_step(steps, "palette_already_visible", {"data": probe.get("data")})
        return ok_json(
            data={
                "palette_ready": True,
                "lep_command": cmd,
                "skipped_command_input": True,
                "open_dwg_path": dwg or None,
                "open_dwg_applied_on_launch": bool(dwg and need_launch),
                "steps": steps,
            },
            message="nanocad_lep_prepare",
            request_id=rid,
        )

    click = _loads(
        uia_tools.uia_click(
            process_name=PROCESS_NCAD,
            title_contains=None,
            automation_id=CMDLINE_AUTOMATION_ID,
            name=None,
            control_type=None,
            nth=0,
            client_request_id=rid,
        )
    )
    _append_step(steps, "uia_click_command_line", {"ok": click.get("ok"), "code": click.get("code"), "data": click.get("data")})
    if not click.get("ok"):
        return err_json(
            str(click.get("code") or "ERR_NOT_FOUND"),
            str(click.get("message") or "command line (1011) not found"),
            data={"steps": steps},
            request_id=rid,
        )
    time.sleep(0.2)

    keys = _loads(
        uia_tools.send_keys(
            process_name=PROCESS_NCAD,
            title_contains=None,
            text=cmd,
            with_enter=True,
            client_request_id=rid,
        )
    )
    _append_step(steps, "send_keys_lep", {"ok": keys.get("ok"), "data": keys.get("data")})
    if not keys.get("ok"):
        return err_json(
            str(keys.get("code") or "ERR_UIA"),
            str(keys.get("message") or "send_keys failed"),
            data={"steps": steps},
            request_id=rid,
        )

    wf = _loads(
        uia_tools.wait_for(
            process_name=PROCESS_NCAD,
            title_contains=None,
            automation_id=PALETTE_ANCHOR_ID,
            name=None,
            timeout_sec=float(wait_palette_timeout_sec),
            poll_sec=wait_palette_poll_sec,
            client_request_id=rid,
        )
    )
    _append_step(steps, "wait_for_lep_palette_root", {"ok": wf.get("ok"), "data": wf.get("data")})
    if not wf.get("ok"):
        return err_json(
            str(wf.get("code") or "ERR_TIMEOUT"),
            str(wf.get("message") or "palette not found"),
            data={"steps": steps, "wait_for": wf.get("data")},
            request_id=rid,
        )

    return ok_json(
        data={
            "palette_ready": True,
            "lep_command": cmd,
            "open_dwg_path": dwg or None,
            "open_dwg_applied_on_launch": bool(dwg and need_launch),
            "steps": steps,
        },
        message="nanocad_lep_prepare",
        request_id=rid,
    )

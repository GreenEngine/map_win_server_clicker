"""
LEP Windows MCP server: Streamable HTTP + UI Automation tools + self-update.

Каждый инструмент возвращает строку с **валидным JSON** (конверт protocol):
ok, code, message, protocol_version, request_id, server_time_utc, data.

Запуск (на Windows):
  set MCP_HOST=0.0.0.0
  set MCP_PORT=8765
  python src/server.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from mcp.server.fastmcp import FastMCP

from src import uia_tools
from src import nanocad_bootstrap
from src import session as session_mod
from src import update as update_mod
from src import action_json_log
from src import learn_log
from src import lep_qa_catalog as lep_qa_catalog_mod
from src import lep_scenario_runner
from src.action_json_log import tool_log_decorator
from src.protocol import err_json, ok_json, parse_request_id

_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
_PORT = int(os.environ.get("MCP_PORT", "8765"))
_STATELESS = os.environ.get("MCP_STATELESS_HTTP", "").lower() in ("1", "true", "yes")

# Дефолт для lep_run_scenario_sequence: приёмка MCP + полный обход палитры одним вызовом.
_DEFAULT_SCENARIO_SEQUENCE_CSV = "lep_mcp_full_operability_smoke.json,lep_plugin_full_palette_uia.json"


def _lep_execute_loaded_scenario(data: dict[str, Any], path: Path, rid: str) -> str:
    """Общее выполнение уже загруженного и валидированного сценария (только Windows)."""
    mod = sys.modules[__name__]

    def _get_tool(name: str):
        fn = getattr(mod, name, None)
        if fn is None or not callable(fn):
            raise RuntimeError(f"unknown tool: {name}")
        return fn

    prefix = str(data.get("id", "scenario"))[:40]
    ok, log = lep_scenario_runner.run_scenario_json(data, get_tool=_get_tool, id_prefix=prefix)
    failed_ns = [e["n"] for e in log if not e.get("ok")]
    base_data: dict[str, Any] = {
        "scenario": str(path),
        "steps_run": len(log),
        "step_log": log,
        "all_steps_ok": ok,
        "failed_step_numbers": failed_ns,
        "stop_on_first_error": bool(data.get("stop_on_first_error", True)),
    }
    if ok:
        return ok_json(data=base_data, message="lep_run_scenario", request_id=rid)
    last = log[-1] if log else {}
    if data.get("stop_on_first_error") is False and len(log) == len(data.get("steps") or []):
        return err_json(
            "ERR_SCENARIO_PARTIAL",
            f"Сценарий выполнен полностью; ошибки на шагах: {failed_ns}",
            data=base_data,
            request_id=rid,
        )
    return err_json(
        str(last.get("code") or "ERR_SCENARIO_STEP"),
        str(last.get("message") or "step failed"),
        data=base_data,
        request_id=rid,
    )


# server_update: если переменная не задана или пустая — по умолчанию разрешено. Явно 0/false/no — отключение.
_mcp_su = os.environ.get("MCP_ALLOW_SELF_UPDATE")
if _mcp_su is None or str(_mcp_su).strip() == "":
    os.environ["MCP_ALLOW_SELF_UPDATE"] = "1"

# После успешного server_update — перезапуск процесса (см. update.schedule_restart_after_update). Отключить: 0/false/no.
_mcp_ra = os.environ.get("MCP_RESTART_AFTER_UPDATE")
if _mcp_ra is None or str(_mcp_ra).strip() == "":
    os.environ["MCP_RESTART_AFTER_UPDATE"] = "1"

# На Windows по умолчанию git/pip через scripts/update_server.ps1 + перезапуск из PS (см. update.py). Отключить: MCP_UPDATE_USE_PS1=0.
if sys.platform == "win32":
    _mcp_ps1 = os.environ.get("MCP_UPDATE_USE_PS1")
    if _mcp_ps1 is None or str(_mcp_ps1).strip() == "":
        os.environ["MCP_UPDATE_USE_PS1"] = "1"

# launch_process: по умолчанию ВКЛ (часто в среде уже стоит MCP_ALLOW_LAUNCH=0 из старых скриптов).
# Явный запрет только: MCP_BLOCK_LAUNCH=1 (или true / yes).
if os.environ.get("MCP_BLOCK_LAUNCH", "").strip().lower() in ("1", "true", "yes"):
    os.environ["MCP_ALLOW_LAUNCH"] = "0"
else:
    os.environ["MCP_ALLOW_LAUNCH"] = "1"

mcp = FastMCP(
    "LEP Windows UI MCP",
    host=_HOST,
    port=_PORT,
    stateless_http=_STATELESS,
    streamable_http_path="/mcp",
)


@mcp.tool()
@tool_log_decorator("health")
def health(client_request_id: str | None = None) -> str:
    """Проверка связи: всегда ok=true при живом процессе. Вызывайте первым."""
    rid = parse_request_id(client_request_id)
    return ok_json(
        data={"status": "alive", "host": _HOST, "port": _PORT},
        message="health",
        request_id=rid,
    )


@mcp.tool()
@tool_log_decorator("lep_qa_catalog")
def lep_qa_catalog(client_request_id: str | None = None) -> str:
    """
    Каталог JSON-сценариев LEP, пути к матрице QA, рекомендуемый порядок вызовов MCP для полного smoke/UI-теста.
    Без UIA — можно вызывать первым после agent_session для планирования прогона на Windows.
    """
    rid = parse_request_id(client_request_id)
    return ok_json(
        data=lep_qa_catalog_mod.lep_qa_catalog_payload(),
        message="lep_qa_catalog",
        request_id=rid,
    )


@mcp.tool()
@tool_log_decorator("agent_session")
def agent_session(client_request_id: str | None = None) -> str:
    """Снимок для агента: protocol_version, список инструментов, workflow, безопасные env, контракт ответов."""
    rid = parse_request_id(client_request_id)
    return ok_json(data=session_mod.agent_session_payload(), message="agent_session", request_id=rid)


@mcp.tool()
@tool_log_decorator("server_info")
def server_info(client_request_id: str | None = None) -> str:
    """Версия Python, пути, git — внутри data (плоская структура)."""
    rid = parse_request_id(client_request_id)
    return ok_json(data=update_mod.server_version_dict(), message="server_info", request_id=rid)


@mcp.tool()
@tool_log_decorator("server_update")
def server_update(mode: str = "pip", client_request_id: str | None = None) -> str:
    """
    Обновление: pip / git_pull / full. Требует MCP_ALLOW_SELF_UPDATE=1.
    По умолчанию фоновое (data.update_async): ответ сразу, git/pip в потоке, итог в logs/mcp_self_update.log.
    Синхронно: MCP_UPDATE_SYNC=1. При ошибке ok=false, code=ERR_UPDATE.
    """
    rid = parse_request_id(client_request_id)
    ok, log, restart_scheduled, update_async = update_mod.run_self_update(mode)
    if ok:
        return ok_json(
            data={
                "log": log,
                "mode": mode,
                "restart_scheduled": restart_scheduled,
                "update_async": update_async,
            },
            message="server_update",
            request_id=rid,
        )
    code = "ERR_FORBIDDEN" if "отключ" in (log or "").lower() else "ERR_UPDATE"
    return err_json(code, log or "update failed", data={"log": log, "mode": mode}, request_id=rid)


@mcp.tool()
@tool_log_decorator("uia_list")
def uia_list(
    process_name: str | None = None,
    title_contains: str | None = None,
    max_depth: int = 6,
    max_nodes: int = 400,
    client_request_id: str | None = None,
) -> str:
    """Список элементов UI (JSON-конверт, элементы в data.items)."""
    return uia_tools.uia_list(process_name, title_contains, max_depth, max_nodes, client_request_id)


@mcp.tool()
@tool_log_decorator("uia_list_subtree")
def uia_list_subtree(
    process_name: str | None = None,
    title_contains: str | None = None,
    anchor_automation_id: str | None = "lep_palette_root",
    anchor_name_contains: str | None = None,
    max_depth: int = 12,
    max_nodes: int = 1200,
    client_request_id: str | None = None,
) -> str:
    """
    Список UI только под якорём палитры LEP (по умолчанию automation_id lep_palette_root),
    без обхода всей ленты nCAD.exe — меньше data.truncated на подвкладках «Создание» / «Анализ».
    """
    return uia_tools.uia_list_subtree(
        process_name,
        title_contains,
        anchor_automation_id,
        anchor_name_contains,
        max_depth,
        max_nodes,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("uia_click")
def uia_click(
    process_name: str | None = None,
    title_contains: str | None = None,
    automation_id: str | None = None,
    name: str | None = None,
    control_type: str | None = None,
    nth: int = 0,
    client_request_id: str | None = None,
) -> str:
    """Клик по элементу (nth при нескольких совпадениях)."""
    return uia_tools.uia_click(
        process_name,
        title_contains,
        automation_id,
        name,
        control_type,
        nth,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("wait_for_element")
def wait_for_element(
    process_name: str | None = None,
    title_contains: str | None = None,
    automation_id: str | None = None,
    name: str | None = None,
    timeout_sec: float = 30.0,
    client_request_id: str | None = None,
) -> str:
    """Ждать появления элемента; при таймауте code=ERR_TIMEOUT."""
    return uia_tools.wait_for(
        process_name,
        title_contains,
        automation_id,
        name,
        timeout_sec,
        0.5,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("uia_modal_ok")
def uia_modal_ok(
    title_regex: str | None = None,
    button_titles: str = "OK,ОК",
    max_window_width: int = 1400,
    max_window_height: int = 950,
    timeout_sec: float = 5.0,
    owner_process_name: str | None = "nCAD.exe",
    client_request_id: str | None = None,
) -> str:
    """
    Найти модальное окно (MessageBox / диалог поверх nanoCAD) по заголовку или классу #32770
    и нажать первую найденную кнопку из button_titles. Не зависит от process_name главного окна.
    owner_process_name: приоритет owned-модалок от nCAD в Win32-фолбэке; пустая строка — отключить.
    """
    return uia_tools.uia_modal_ok(
        title_regex,
        button_titles,
        max_window_width,
        max_window_height,
        timeout_sec,
        owner_process_name,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("uia_modal_titlebar_close")
def uia_modal_titlebar_close(
    title_regex: str | None = None,
    max_window_width: int = 1400,
    max_window_height: int = 950,
    timeout_sec: float = 5.0,
    client_request_id: str | None = None,
) -> str:
    """Закрыть модалку кликом по крестику [X] в заголовке (экранные координаты от UIA + DPI)."""
    return uia_tools.uia_modal_titlebar_close(
        title_regex,
        max_window_width,
        max_window_height,
        timeout_sec,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("mouse_click")
def mouse_click(
    screen_x: int,
    screen_y: int,
    button: str = "left",
    double: bool = False,
    client_request_id: str | None = None,
) -> str:
    """Клик мыши в экранных координатах (например крестик по расчёту от capture_monitor)."""
    return uia_tools.mouse_click(screen_x, screen_y, button, double, client_request_id)


@mcp.tool()
@tool_log_decorator("mouse_click_window")
def mouse_click_window(
    client_x: int,
    client_y: int,
    process_name: str | None = None,
    title_contains: str | None = None,
    button: str = "left",
    double: bool = False,
    client_request_id: str | None = None,
) -> str:
    """Клик в клиентских координатах окна (ClientToScreen); надёжнее DPI, чем голый screen_x/y от bbox."""
    return uia_tools.mouse_click_window(
        client_x,
        client_y,
        process_name,
        title_contains,
        button,
        double,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("mouse_move")
def mouse_move(
    screen_x: int,
    screen_y: int,
    client_request_id: str | None = None,
) -> str:
    """Переместить курсор в экранные координаты без клика (чтобы было видно на RDP)."""
    return uia_tools.mouse_move(screen_x, screen_y, client_request_id)


@mcp.tool()
@tool_log_decorator("mouse_move_smooth")
def mouse_move_smooth(
    screen_x: int,
    screen_y: int,
    steps: int = 28,
    pause_ms: float = 18.0,
    client_request_id: str | None = None,
) -> str:
    """
    Плавно провести курсор к точке (от текущей позиции по прямой).
    Перед кликом по модалке вызывайте это — наблюдатель увидит движение мыши.
    """
    return uia_tools.mouse_move_smooth(screen_x, screen_y, steps, pause_ms, client_request_id)


@mcp.tool()
@tool_log_decorator("send_keys")
def send_keys(
    process_name: str | None = None,
    title_contains: str | None = None,
    text: str = "",
    with_enter: bool = False,
    client_request_id: str | None = None,
) -> str:
    """Ввод текста в окно."""
    return uia_tools.send_keys(process_name, title_contains, text, with_enter, client_request_id)


@mcp.tool()
@tool_log_decorator("capture_window")
def capture_window(
    process_name: str | None = None,
    title_contains: str | None = None,
    out_path: str | None = None,
    filename_suffix: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    """
    PNG снимок окна: data.path на Windows.
    При include_base64=True в data.png_base64 — картинка для удалённого клиента (Mac и т.д.).
    max_edge_px>0 ограничивает большую сторону встраиваемого PNG; файл на диске — полный кадр.
    filename_suffix: если out_path не задан — фрагмент имени (латиница); иначе подстановка из заголовка окна (data.filename_slug_used).
    """
    return uia_tools.capture_window(
        process_name,
        title_contains,
        out_path,
        filename_suffix,
        include_base64,
        max_edge_px,
        client_request_id,
    )


@mcp.tool()
@tool_log_decorator("launch_process")
def launch_process(
    executable: str,
    arguments: str = "",
    wait_timeout_sec: float = 90.0,
    client_request_id: str | None = None,
) -> str:
    """
    Запуск .exe на Windows. Нужен MCP_ALLOW_LAUNCH=1 на сервере.
    executable: полный путь или AUTO / AUTO_NANOCAD (поиск nCAD.exe).
    После старта ждёт появления процесса в UIA (до wait_timeout_sec).
    """
    return uia_tools.launch_process(executable, arguments, wait_timeout_sec, client_request_id)


@mcp.tool()
def action_json_log_recent(max_lines: int = 40, client_request_id: str | None = None) -> str:
    """
    Последние записи из JSONL-лога успешных действий (см. MCP_ACTION_JSONL в README).
    Если лог выключен — data.enabled=false. Дедупликация сценария: смотреть action_signature / replay_hint.
    """
    rid = parse_request_id(client_request_id)
    ok, msg, items = action_json_log.read_recent_entries(max_lines)
    if not ok and msg == "MCP_ACTION_JSONL не задан":
        return ok_json(
            data={"enabled": False, "entries": [], "hint": msg},
            message="action_json_log_recent",
            request_id=rid,
        )
    if not ok:
        return err_json("ERR_IO", msg, request_id=rid)
    log_path = (os.environ.get("MCP_ACTION_JSONL") or "").strip()
    return ok_json(
        data={
            "enabled": True,
            "path": log_path,
            "filter": (os.environ.get("MCP_ACTION_JSONL_FILTER") or "lep_only").strip(),
            "entries": items,
            "count": len(items),
        },
        message="action_json_log_recent",
        request_id=rid,
    )


@mcp.tool()
def learn_log_recent(max_lines: int = 40, client_request_id: str | None = None) -> str:
    """
    Последние записи из JSONL корпуса наблюдений (MCP_LEARN_JSONL).
    Только чтение; данные не влияют на поведение инструментов. Если лог выключен — data.enabled=false.
    """
    rid = parse_request_id(client_request_id)
    ok, msg, items = learn_log.read_recent_entries(max_lines)
    if not ok and msg == "MCP_LEARN_JSONL не задан":
        return ok_json(
            data={"enabled": False, "entries": [], "hint": msg},
            message="learn_log_recent",
            request_id=rid,
        )
    if not ok:
        return err_json("ERR_IO", msg, request_id=rid)
    log_path = (os.environ.get("MCP_LEARN_JSONL") or "").strip()
    return ok_json(
        data={
            "enabled": True,
            "path": log_path,
            "filter": (os.environ.get("MCP_LEARN_FILTER") or "lep_only").strip(),
            "include_failures": os.environ.get("MCP_LEARN_INCLUDE_FAILURES", "").strip().lower()
            in ("1", "true", "yes"),
            "entries": items,
            "count": len(items),
        },
        message="learn_log_recent",
        request_id=rid,
    )


@mcp.tool()
@tool_log_decorator("nanocad_lep_prepare")
def nanocad_lep_prepare(
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
    client_request_id: str | None = None,
) -> str:
    """
    Один вызов: nanoCAD (если ещё не в UIA — launch_process AUTO_NANOCAD), закрытие типовых модалок,
    фокус командной строки (1011), команда LEP (+ Enter), ожидание lep_palette_root.
    Логика вынесена в `src/nanocad_bootstrap.py`. Нужен MCP_ALLOW_LAUNCH=1 для старта процесса.
    skip_launch_if_running=false — принудительный launch даже при уже запущенном nCAD (осторожно: второй экземпляр).
    lep_command: по умолчанию из MCP_LEP_COMMAND или «LEP».
    open_dwg_path: .dwg при холодном старте nCAD (аргумент командной строки); иначе MCP_LEP_OPEN_DWG / LEP_GOLDEN_DWG.
    """
    return nanocad_bootstrap.nanocad_lep_prepare(
        skip_launch_if_running=skip_launch_if_running,
        launch_arguments=launch_arguments,
        open_dwg_path=open_dwg_path,
        launch_wait_timeout_sec=launch_wait_timeout_sec,
        modal_rounds=modal_rounds,
        modal_timeout_sec=modal_timeout_sec,
        modal_button_titles=modal_button_titles,
        after_modal_titlebar_rounds=after_modal_titlebar_rounds,
        lep_command=lep_command,
        wait_palette_timeout_sec=wait_palette_timeout_sec,
        wait_palette_poll_sec=0.45,
        client_request_id=client_request_id,
    )


@mcp.tool()
@tool_log_decorator("lep_run_scenario")
def lep_run_scenario(
    scenario_name: str,
    stop_on_first_error: bool | None = None,
    client_request_id: str | None = None,
) -> str:
    """
    Выполнить JSON-сценарий из каталога scenarios/ по имени файла (без path traversal).
    Шаги вызывают те же функции, что и MCP-инструменты — один вызов для автономного прогона на ВМ без Cursor.
    Только Windows; сценарий должен быть version=1 и только с invoke из белого списка (см. lep_scenario_runner).
    stop_on_first_error: если задан (true/false), переопределяет поле с тем же именем в JSON для этого прогона.
    """
    rid = parse_request_id(client_request_id)
    if sys.platform != "win32":
        return err_json("ERR_PLATFORM", "lep_run_scenario только на Windows", request_id=rid)
    scenarios_root = Path(__file__).resolve().parent.parent / "scenarios"
    try:
        path = lep_scenario_runner.resolve_scenario_path_under_root(scenario_name, scenarios_root)
        data = lep_scenario_runner.load_scenario_dict(path)
        if stop_on_first_error is not None:
            data = dict(data)
            data["stop_on_first_error"] = bool(stop_on_first_error)
        lep_scenario_runner.validate_scenario(data, path)
    except FileNotFoundError as e:
        return err_json("ERR_NOT_FOUND", str(e), request_id=rid)
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)

    return _lep_execute_loaded_scenario(data, path, rid)


@mcp.tool()
@tool_log_decorator("lep_run_scenario_sequence")
def lep_run_scenario_sequence(
    scenario_names_csv: str | None = None,
    client_request_id: str | None = None,
) -> str:
    """
    Несколько JSON-сценариев подряд одним вызовом MCP (автономная приёмка: smoke + палитра и т.д.).
    scenario_names_csv: имена файлов через запятую, как у lep_run_scenario (без path traversal).
    По умолчанию: lep_mcp_full_operability_smoke.json, lep_plugin_full_palette_uia.json.
    Итог: data.runs[] с тем же составом полей, что у одного lep_run_scenario; data.all_scenarios_ok — true только если каждый прогон завершился с ok=true на верхнем уровне ответа (включ. ERR_SCENARIO_PARTIAL считается ok=false для агрегата, если внутри all_steps_ok=false).
    """
    rid = parse_request_id(client_request_id)
    if sys.platform != "win32":
        return err_json("ERR_PLATFORM", "lep_run_scenario_sequence только на Windows", request_id=rid)
    raw = (scenario_names_csv or "").strip() or _DEFAULT_SCENARIO_SEQUENCE_CSV
    names = [s.strip() for s in raw.split(",") if s.strip()][:8]
    if not names:
        return err_json("ERR_VALIDATION", "Пустой список сценариев", request_id=rid)

    scenarios_root = Path(__file__).resolve().parent.parent / "scenarios"
    runs: list[dict[str, Any]] = []
    aggregate_ok = True

    for scenario_name in names:
        try:
            path = lep_scenario_runner.resolve_scenario_path_under_root(scenario_name, scenarios_root)
            data = lep_scenario_runner.load_scenario_dict(path)
            lep_scenario_runner.validate_scenario(data, path)
        except FileNotFoundError as e:
            aggregate_ok = False
            runs.append({"scenario_name": scenario_name, "error": "ERR_NOT_FOUND", "message": str(e)})
            break
        except ValueError as e:
            aggregate_ok = False
            runs.append({"scenario_name": scenario_name, "error": "ERR_VALIDATION", "message": str(e)})
            break

        one = _lep_execute_loaded_scenario(data, path, rid)
        body = json.loads(one)
        inner = body.get("data") if isinstance(body.get("data"), dict) else {}
        steps_ok = inner.get("all_steps_ok")
        entry: dict[str, Any] = {
            "scenario_name": scenario_name,
            "scenario_path": str(path),
            "top_ok": body.get("ok") is True,
            "top_code": body.get("code"),
            "all_steps_ok": steps_ok,
            "failed_step_numbers": inner.get("failed_step_numbers"),
            "steps_run": inner.get("steps_run"),
        }
        runs.append(entry)
        if steps_ok is not True:
            aggregate_ok = False

    payload: dict[str, Any] = {
        "scenario_names_csv": raw,
        "runs": runs,
        "all_scenarios_ok": aggregate_ok,
    }
    if aggregate_ok:
        return ok_json(data=payload, message="lep_run_scenario_sequence", request_id=rid)
    return err_json(
        "ERR_SCENARIO_SEQUENCE",
        "Один или несколько сценариев завершились с ошибкой; см. data.runs",
        data=payload,
        request_id=rid,
    )


@mcp.tool()
@tool_log_decorator("capture_monitor")
def capture_monitor(
    monitor_index: int = 1,
    out_path: str | None = None,
    filename_suffix: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    """
    Снимок всего монитора (MSS), без привязки к окну процесса.
    monitor_index: 0 — все мониторы одним кадром, 1 — основной (часто нужен он).
    filename_suffix: если out_path не задан — фрагмент имени PNG (каталог MCP_CAPTURE_DIR или temp).
    Если после отключения RDP кадр чёрный — смотрите data.content_hint и README (виртуальный дисплей).
    """
    return uia_tools.capture_monitor(
        monitor_index,
        out_path,
        filename_suffix,
        include_base64,
        max_edge_px,
        client_request_id,
    )


def _local_ipv4_candidates() -> list[str]:
    """IPv4 этой машины без loopback (для лога при старте)."""
    order: list[str] = []
    seen: set[str] = set()

    def add(ip: str) -> None:
        if not ip or ip.startswith("127."):
            return
        if ip not in seen:
            seen.add(ip)
            order.append(ip)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            add(info[4][0])
    except OSError:
        pass
    return order


def _print_listen_banner() -> None:
    ips = _local_ipv4_candidates()
    path = getattr(mcp, "streamable_http_path", None) or "/mcp"
    bind = f"{_HOST}:{_PORT}"
    print(f"[MCP] Слушаю {bind}, путь {path}", flush=True)
    if ips:
        joined = ", ".join(ips)
        print(f"[MCP] IPv4 этой машины: {joined}", flush=True)
        if _HOST in ("0.0.0.0", "::"):
            primary = ips[0]
            print(f"[MCP] Пример URL для клиента в сети: http://{primary}:{_PORT}{path}", flush=True)
    else:
        print("[MCP] Не удалось определить IPv4 (смотрите ipconfig / ifconfig).", flush=True)


def main() -> None:
    _print_listen_banner()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()

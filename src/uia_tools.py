"""UI Automation helpers (pywinauto). Windows only. Все ответы — JSON-конверт protocol."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

from src.protocol import err_json, ok_json, parse_request_id


def _require_win() -> None:
    if sys.platform != "win32":
        raise RuntimeError("ERR_PLATFORM")


def _env_launch_allowed() -> bool:
    return os.environ.get("MCP_ALLOW_LAUNCH", "").strip().lower() in ("1", "true", "yes")


def _resolve_nanocad_executable(explicit: str) -> str | None:
    """Полный путь к nCAD.exe или None. explicit=AUTO / AUTO_NANOCAD — PATH, MCP_NANOCAD_EXE, типовые пути, glob Nanosoft."""
    import glob
    import shutil

    ex = (explicit or "").strip()
    if ex and os.path.isfile(ex):
        return ex
    key = ex.upper()
    if key not in ("AUTO", "AUTO_NANOCAD", ""):
        return None
    envp = (os.environ.get("MCP_NANOCAD_EXE") or "").strip()
    if envp and os.path.isfile(envp):
        return envp
    w = shutil.which("nCAD.exe")
    if w and os.path.isfile(w):
        return w
    candidates = [
        r"C:\Program Files\Nanosoft\nanoCAD 26.0\nCAD.exe",
        r"C:\Program Files (x86)\Nanosoft\nanoCAD 26.0\nCAD.exe",
        r"C:\Program Files\Nanosoft\nanoCAD 25.0\nCAD.exe",
        r"C:\Program Files (x86)\Nanosoft\nanoCAD 25.0\nCAD.exe",
        r"C:\Program Files\Nanosoft\nanoCAD 24.0\nCAD.exe",
        r"C:\Program Files (x86)\Nanosoft\nanoCAD 24.0\nCAD.exe",
        r"C:\Program Files\Nanosoft\nanoCAD 23.1\nCAD.exe",
        r"C:\Program Files (x86)\Nanosoft\nanoCAD 23.1\nCAD.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    for pattern in (
        r"C:\Program Files\Nanosoft\**\nCAD.exe",
        r"C:\Program Files (x86)\Nanosoft\**\nCAD.exe",
    ):
        try:
            found = glob.glob(pattern, recursive=True)
        except Exception:
            continue
        for p in found:
            if os.path.isfile(p):
                return p
    return None


def launch_process(
    executable: str,
    arguments: str = "",
    wait_timeout_sec: float = 90.0,
    client_request_id: str | None = None,
) -> str:
    """
    Запуск процесса (Windows). Требует MCP_ALLOW_LAUNCH=1.
    executable: полный путь к .exe или AUTO / AUTO_NANOCAD — поиск nCAD.exe.
    После старта ждёт появления процесса в UIA до wait_timeout_sec.
    """
    import shlex
    import subprocess

    rid = parse_request_id(client_request_id)
    try:
        if sys.platform != "win32":
            return err_json("ERR_PLATFORM", "launch_process только на Windows", request_id=rid)
        if not _env_launch_allowed():
            return err_json(
                "ERR_FORBIDDEN",
                "Запуск процессов отключён (MCP_BLOCK_LAUNCH=1). Уберите блокировку и перезапустите MCP.",
                request_id=rid,
            )
        raw = (executable or "").strip()
        if not raw:
            return err_json("ERR_VALIDATION", "Укажите executable (полный путь или AUTO / AUTO_NANOCAD)", request_id=rid)
        if raw.upper() in ("AUTO", "AUTO_NANOCAD"):
            exe = _resolve_nanocad_executable("AUTO")
        else:
            exe = raw if os.path.isfile(raw) else None
        if not exe:
            return err_json(
                "ERR_VALIDATION",
                f"Исполняемый файл не найден: {raw!r}. Укажите полный путь к nCAD.exe или задайте "
                "переменную окружения MCP_NANOCAD_EXE и перезапустите MCP.",
                request_id=rid,
            )
        argv = [exe]
        if (arguments or "").strip():
            try:
                argv.extend(shlex.split(arguments, posix=False))
            except ValueError as e:
                return err_json("ERR_VALIDATION", f"arguments: {e}", request_id=rid)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = int(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)

        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
        from pywinauto import Application

        proc_name = os.path.basename(exe)
        deadline = time.monotonic() + max(5.0, float(wait_timeout_sec))
        last_err = ""
        waited = 0.0
        t0 = time.monotonic()
        while time.monotonic() < deadline:
            try:
                app = Application(backend="uia").connect(path=proc_name, timeout=3)
                tw = app.top_window()
                tw.wait("exists", timeout=3)
                waited = time.monotonic() - t0
                try:
                    tw_name = tw.window_text()
                except Exception:
                    tw_name = str(tw)
                return ok_json(
                    data={
                        "executable": exe,
                        "process_name": proc_name,
                        "arguments": arguments,
                        "waited_sec": round(waited, 2),
                        "top_window": tw_name,
                    },
                    message="launch_process",
                    request_id=rid,
                )
            except Exception as e:
                last_err = str(e)
                time.sleep(1.0)
        return err_json(
            "ERR_TIMEOUT",
            "Процесс не появился в UIA за отведённое время",
            data={"executable": exe, "last_error": last_err},
            request_id=rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def _rect_dict(ctrl: Any) -> dict[str, int] | None:
    try:
        r = ctrl.rectangle()
        return {"left": int(r.left), "top": int(r.top), "right": int(r.right), "bottom": int(r.bottom)}
    except Exception:
        return None


def _walk(
    ctrl: Any,
    depth: int,
    max_depth: int,
    max_nodes: int,
    out: list[dict[str, Any]],
    truncated: list[bool],
) -> None:
    if len(out) >= max_nodes:
        truncated[0] = True
        return
    if depth > max_depth:
        truncated[0] = True
        return
    try:
        info = ctrl.element_info
        out.append(
            {
                "depth": depth,
                "name": getattr(info, "name", "") or "",
                "automation_id": getattr(info, "automation_id", "") or "",
                "control_type": str(getattr(info, "control_type", "")),
                "class_name": getattr(info, "class_name", "") or "",
                "rectangle": _rect_dict(ctrl),
            }
        )
    except Exception as ex:
        out.append({"depth": depth, "error": str(ex)})
        return
    # WinForms DataGrid раздувает дерево (сотни ячеек/строк) и съедает max_nodes до соседних
    # вкладок палитры («Генератор», «Расчёты»). Сам узел оставляем, вложенность не обходим.
    try:
        ct = str(getattr(info, "control_type", "") or "")
        cn = (getattr(info, "class_name", "") or "").lower()
        if "DataGrid" in ct or "datagrid" in cn:
            return
    except Exception:
        pass
    try:
        children = ctrl.children()
    except Exception:
        return
    for ch in children:
        _walk(ch, depth + 1, max_depth, max_nodes, out, truncated)


# Лимит обхода descendants при поиске клика/ожидания; малый лимит не находит кнопки
# на вкладках LEP после тяжёлых панелей («Трасса» / DataGrid).
_MAX_DESC_SCAN = 20000


def _descendants_matching(
    w: Any,
    automation_id: str | None,
    name: str | None,
    control_type: str | None,
) -> list[Any]:
    """
    pywinauto 0.6.x: descendants() не всегда принимает auto_id в UIA build_condition.
    Тогда обходим дерево и фильтруем по element_info.
    """
    crit: dict[str, Any] = {}
    if automation_id:
        crit["auto_id"] = automation_id
    if name:
        crit["title"] = name
    if control_type:
        crit["control_type"] = control_type
    try:
        return list(w.descendants(**crit))
    except TypeError:
        pass
    matches: list[Any] = []
    want_aid = (automation_id or "").strip()
    want_name = (name or "").strip()
    want_ct = (control_type or "").strip()
    scanned = 0
    for el in w.descendants():
        scanned += 1
        if scanned > _MAX_DESC_SCAN:
            break
        try:
            info = el.element_info
            aid = (getattr(info, "automation_id", None) or "") or ""
            nm = (getattr(info, "name", None) or "") or ""
            ct = str(getattr(info, "control_type", "") or "")
            if want_aid and aid != want_aid:
                continue
            if want_name and nm != want_name:
                continue
            if want_ct and (want_ct not in ct) and (not ct.endswith(want_ct)):
                continue
            matches.append(el)
        except Exception:
            continue
    return matches


def _resolve_top_window(process_name: str | None, title_contains: str | None) -> Any:
    _require_win()
    from pywinauto import Application, Desktop

    desktop = Desktop(backend="uia")
    if title_contains:
        pat = f".*{re.escape(title_contains)}.*"
        w = desktop.window(title_re=pat, top_level_only=True)
        w.wait("exists", timeout=5)
        return w
    if process_name:
        app = Application(backend="uia").connect(path=process_name)
        w = app.top_window()
        w.wait("exists", timeout=5)
        return w
    raise ValueError("Укажите process_name (например notepad.exe) или title_contains")


def uia_list(
    process_name: str | None = None,
    title_contains: str | None = None,
    max_depth: int = 6,
    max_nodes: int = 400,
    client_request_id: str | None = None,
) -> str:
    """Плоский список элементов окна в data.items; data.truncated если обрезано по лимитам."""
    rid = parse_request_id(client_request_id)
    try:
        w = _resolve_top_window(process_name, title_contains)
        out: list[dict[str, Any]] = []
        truncated = [False]
        md = max(1, min(int(max_depth), 20))
        mn = max(10, min(int(max_nodes), 5000))
        _walk(w, 0, md, mn, out, truncated)
        return ok_json(
            data={
                "items": out,
                "count": len(out),
                "truncated": truncated[0],
                "limits": {"max_depth": md, "max_nodes": mn},
                "target": {"process_name": process_name, "title_contains": title_contains},
            },
            message="uia_list",
            request_id=rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except RuntimeError as e:
        if str(e) == "ERR_PLATFORM":
            return err_json(
                "ERR_PLATFORM",
                "UIA доступен только на Windows с pywinauto.",
                data={"platform": sys.platform},
                request_id=rid,
            )
        return err_json("ERR_UIA", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def uia_click(
    process_name: str | None = None,
    title_contains: str | None = None,
    automation_id: str | None = None,
    name: str | None = None,
    control_type: str | None = None,
    nth: int = 0,
    client_request_id: str | None = None,
) -> str:
    rid = parse_request_id(client_request_id)
    try:
        w = _resolve_top_window(process_name, title_contains)
        crit: dict[str, Any] = {}
        if automation_id:
            crit["auto_id"] = automation_id
        if name:
            crit["title"] = name
        if control_type:
            crit["control_type"] = control_type
        if not crit:
            return err_json(
                "ERR_VALIDATION",
                "Нужен хотя бы один из: automation_id, name, control_type",
                request_id=rid,
            )
        matches = _descendants_matching(w, automation_id, name, control_type)
        if not matches:
            return err_json(
                "ERR_NOT_FOUND",
                "Элементы не найдены",
                data={"criteria": crit},
                request_id=rid,
            )
        if nth < 0 or nth >= len(matches):
            return err_json(
                "ERR_VALIDATION",
                f"nth вне диапазона 0..{len(matches) - 1}",
                data={"matches": len(matches)},
                request_id=rid,
            )
        target = matches[nth]
        target.click_input()
        return ok_json(
            data={
                "clicked_index": nth,
                "matches_total": len(matches),
                "element_info": str(target.element_info),
            },
            message="uia_click",
            request_id=rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except RuntimeError as e:
        if str(e) == "ERR_PLATFORM":
            return err_json("ERR_PLATFORM", "Только Windows.", request_id=rid)
        return err_json("ERR_UIA", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


_DEFAULT_MODAL_TITLE_RE = re.compile(
    r"Внимание|Ошибка|Нет данных|Подтверждение|Информация|Нет данных трассы|"
    r"Анализ трассы|Экспорт|Импорт|Корректировка|Журнал|LEP —|LEP -",
    re.IGNORECASE,
)


def _hwnd_uia(w: Any) -> int:
    try:
        return int(w.handle)
    except Exception:
        try:
            h = getattr(w.element_info, "handle", None)
            return int(h) if h else 0
        except Exception:
            return 0


def _dpi_scale(hwnd: int) -> float:
    """Масштаб относительно 96 DPI (Win10+ GetDpiForWindow)."""
    if not hwnd:
        return 1.0
    try:
        import ctypes

        dpi = int(ctypes.windll.user32.GetDpiForWindow(hwnd))
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def _titlebar_close_screen_coords(rect: Any, scale: float) -> tuple[int, int]:
    """
    Экранные координаты клика по кнопке закрытия [X] в заголовке (не Client area).
    Эвристика для стандартного non-client caption Win32 / #32770.
    """
    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    mx = max(6, int(18 * scale))
    my = max(6, int(14 * scale))
    cx = right - mx
    cy = top + my
    # не уезжать за левую границу узкого окна
    min_x = left + max(16, int(24 * scale))
    if cx < min_x:
        cx = min_x
    if cy >= bottom:
        cy = top + max(8, int(10 * scale))
    return cx, cy


def _modal_candidate_match(
    w: Any,
    pat: re.Pattern,
    max_window_width: int,
    max_window_height: int,
) -> tuple[bool, str, str, int, int]:
    """(ok, title, class_name, rw, rh) для верхнего уровня."""
    try:
        if not w.is_visible():
            return False, "", "", 0, 0
    except Exception:
        return False, "", "", 0, 0
    try:
        r = w.rectangle()
        rw, rh = int(r.width()), int(r.height())
    except Exception:
        return False, "", "", 0, 0
    if rw > int(max_window_width) or rh > int(max_window_height):
        return False, "", "", rw, rh
    try:
        title = (w.window_text() or "").strip()
    except Exception:
        try:
            title = (w.element_info.name or "").strip()
        except Exception:
            title = ""
    try:
        cls = (w.element_info.class_name or "").strip()
    except Exception:
        cls = ""
    is_dialog_shell = "#32770" in cls or "Dialog" in str(getattr(w.element_info, "control_type", ""))
    title_hit = bool(pat.search(title)) if title else False
    small_dialog = is_dialog_shell and rw < 900 and rh < 700
    if not title_hit and not small_dialog:
        return False, title, cls, rw, rh
    return True, title, cls, rw, rh


def uia_modal_ok(
    title_regex: str | None = None,
    button_titles: str = "OK,ОК",
    max_window_width: int = 1400,
    max_window_height: int = 950,
    timeout_sec: float = 5.0,
    client_request_id: str | None = None,
) -> str:
    """
    Закрыть типичный MessageBox Win32 / модалку поверх nanoCAD: обход **top-level** окон Desktop (UIA),
    а не только потомков nCAD.exe — там кнопка OK часто не находится через uia_click(process_name=...).

    - title_regex: если задан — заголовок окна должен совпадать с regex; иначе используется встроенный
      список типичных заголовков LEP / системных диалогов.
    - button_titles: через запятую подписи кнопок в порядке попытки (по умолчанию OK, ОК).
    - max_window_width/height: отсекаем главное окно nanoCAD (большое); модалки обычно меньше.
    """
    rid = parse_request_id(client_request_id)
    _require_win()
    from pywinauto import Desktop

    try:
        pat = re.compile(title_regex, re.IGNORECASE) if (title_regex or "").strip() else _DEFAULT_MODAL_TITLE_RE
    except re.error as e:
        return err_json("ERR_VALIDATION", f"title_regex: {e}", request_id=rid)

    buttons = [x.strip() for x in (button_titles or "OK,ОК").split(",") if x.strip()]
    if not buttons:
        return err_json("ERR_VALIDATION", "Укажите button_titles", request_id=rid)

    d = Desktop(backend="uia")
    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    last_err = ""
    while time.monotonic() < deadline:
        try:
            for w in d.windows():
                try:
                    if not w.is_visible():
                        continue
                except Exception:
                    continue
                ok_c, title, cls, rw, rh = _modal_candidate_match(w, pat, max_window_width, max_window_height)
                if not ok_c:
                    continue
                for bt in buttons:
                    try:
                        ch = w.child_window(title=bt, control_type="Button")
                        if ch.exists(timeout=0.2):
                            ch.click_input()
                            return ok_json(
                                data={
                                    "closed": True,
                                    "window_title": title,
                                    "class_name": cls,
                                    "button": bt,
                                    "size": {"w": rw, "h": rh},
                                },
                                message="uia_modal_ok",
                                request_id=rid,
                            )
                    except Exception as e2:
                        last_err = str(e2)
                        continue
        except Exception as e:
            last_err = str(e)
        time.sleep(0.25)
    return err_json(
        "ERR_NOT_FOUND",
        "Модальное окно с кнопкой из button_titles не найдено за timeout",
        data={"last_error": last_err, "title_regex": title_regex or str(pat.pattern)},
        request_id=rid,
    )


def uia_modal_titlebar_close(
    title_regex: str | None = None,
    max_window_width: int = 1400,
    max_window_height: int = 950,
    timeout_sec: float = 5.0,
    client_request_id: str | None = None,
) -> str:
    """
    Закрыть модалку кликом мыши по **[X]** в заголовке: те же кандидаты, что у `uia_modal_ok`,
    координаты считаются от `rectangle()` окна и DPI (`GetDpiForWindow`).
    """
    rid = parse_request_id(client_request_id)
    _require_win()
    from pywinauto import Desktop, mouse

    try:
        pat = re.compile(title_regex, re.IGNORECASE) if (title_regex or "").strip() else _DEFAULT_MODAL_TITLE_RE
    except re.error as e:
        return err_json("ERR_VALIDATION", f"title_regex: {e}", request_id=rid)

    d = Desktop(backend="uia")
    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    last_err = ""
    while time.monotonic() < deadline:
        try:
            for w in d.windows():
                ok_c, title, cls, rw, rh = _modal_candidate_match(w, pat, max_window_width, max_window_height)
                if not ok_c:
                    continue
                try:
                    r = w.rectangle()
                    hwnd = _hwnd_uia(w)
                    scale = _dpi_scale(hwnd)
                    cx, cy = _titlebar_close_screen_coords(r, scale)
                    mouse.click(button="left", coords=(cx, cy))
                    return ok_json(
                        data={
                            "closed": True,
                            "via": "titlebar_close",
                            "window_title": title,
                            "class_name": cls,
                            "size": {"w": rw, "h": rh},
                            "click_screen": {"x": cx, "y": cy},
                            "dpi_scale": scale,
                        },
                        message="uia_modal_titlebar_close",
                        request_id=rid,
                    )
                except Exception as e2:
                    last_err = str(e2)
                    continue
        except Exception as e:
            last_err = str(e)
        time.sleep(0.25)
    return err_json(
        "ERR_NOT_FOUND",
        "Модальное окно для закрытия по крестику не найдено за timeout",
        data={"last_error": last_err, "title_regex": title_regex or str(pat.pattern)},
        request_id=rid,
    )


def mouse_click(
    screen_x: int,
    screen_y: int,
    button: str = "left",
    double: bool = False,
    client_request_id: str | None = None,
) -> str:
    """
    Клик мыши в **экранных** координатах (полезно, если агент вычислил позицию крестика по `capture_*`).
    button: left | right | middle; double — двойной клик.
    """
    rid = parse_request_id(client_request_id)
    _require_win()
    from pywinauto import mouse

    try:
        x = int(screen_x)
        y = int(screen_y)
    except (TypeError, ValueError):
        return err_json("ERR_VALIDATION", "screen_x и screen_y должны быть целыми", request_id=rid)
    btn = (button or "left").lower().strip()
    if btn not in ("left", "right", "middle"):
        return err_json("ERR_VALIDATION", "button: left | right | middle", request_id=rid)
    try:
        if double:
            mouse.double_click(button=btn, coords=(x, y))
        else:
            mouse.click(button=btn, coords=(x, y))
        return ok_json(
            data={"clicked": True, "screen_x": x, "screen_y": y, "button": btn, "double": bool(double)},
            message="mouse_click",
            request_id=rid,
        )
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def wait_for(
    process_name: str | None = None,
    title_contains: str | None = None,
    automation_id: str | None = None,
    name: str | None = None,
    timeout_sec: float = 30.0,
    poll_sec: float = 0.5,
    client_request_id: str | None = None,
) -> str:
    rid = parse_request_id(client_request_id)
    start = time.monotonic()
    deadline = start + max(1.0, float(timeout_sec))
    last = ""
    while time.monotonic() < deadline:
        try:
            w = _resolve_top_window(process_name, title_contains)
            if not (automation_id or name):
                return err_json(
                    "ERR_VALIDATION",
                    "Нужен automation_id и/или name",
                    request_id=rid,
                )
            if _descendants_matching(w, automation_id, name, None):
                return ok_json(
                    data={"found": True, "waited_sec": round(time.monotonic() - start, 3)},
                    message="wait_for_element",
                    request_id=rid,
                )
        except Exception as e:
            last = str(e)
        time.sleep(max(0.05, float(poll_sec)))
    return err_json(
        "ERR_TIMEOUT",
        "Элемент не появился за отведённое время",
        data={"found": False, "last_error": last},
        request_id=rid,
    )


def send_keys(
    process_name: str | None = None,
    title_contains: str | None = None,
    text: str = "",
    with_enter: bool = False,
    client_request_id: str | None = None,
) -> str:
    rid = parse_request_id(client_request_id)
    try:
        w = _resolve_top_window(process_name, title_contains)
        w.set_focus()
        if text:
            w.type_keys(text, with_spaces=True)
        if with_enter:
            w.type_keys("{ENTER}")
        return ok_json(data={"sent": True, "with_enter": with_enter}, message="send_keys", request_id=rid)
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except RuntimeError as e:
        if str(e) == "ERR_PLATFORM":
            return err_json("ERR_PLATFORM", "Только Windows.", request_id=rid)
        return err_json("ERR_UIA", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def _image_content_hint(img: Any) -> str:
    """Грубая эвристика: чёрный кадр после отключения RDP / без вывода на дисплей."""
    try:
        from PIL import ImageStat

        g = img.convert("L")
        st = ImageStat.Stat(g)
        mean = float(st.mean[0])
        dev = float(st.stddev[0])
        if mean < 6.0 and dev < 5.0:
            return "likely_blank_or_no_video_output"
        return "likely_has_content"
    except Exception:
        return "unknown"


def _save_grab_png(
    shot: Any,
    out_path: str,
    include_base64: bool,
    max_edge_px: int,
    extra_data: dict[str, Any],
    rid: str,
) -> str:
    import base64
    import io

    from PIL import Image

    meta = dict(extra_data)
    msg = str(meta.pop("capture_message", "capture"))

    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    img.save(out_path, "PNG")
    bbox = meta.get("bbox") or {
        "left": int(shot.left),
        "top": int(shot.top),
        "width": int(shot.width),
        "height": int(shot.height),
    }
    data: dict[str, Any] = {"path": out_path, "bbox": bbox, **meta}
    data["content_hint"] = _image_content_hint(img)
    if include_base64:
        enc = img
        scaled = False
        if max_edge_px and max_edge_px > 0:
            mw, mh = img.size
            edge = max(mw, mh)
            if edge > max_edge_px:
                ratio = max_edge_px / float(edge)
                enc = img.resize((int(mw * ratio), int(mh * ratio)), Image.Resampling.LANCZOS)
                scaled = True
        buf = io.BytesIO()
        enc.save(buf, format="PNG")
        data["png_base64"] = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        data["image_mime_type"] = "image/png"
        data["embedded_width"] = enc.width
        data["embedded_height"] = enc.height
        if scaled:
            data["png_scaled_for_transport"] = True
            data["max_edge_px"] = max_edge_px
    return ok_json(data=data, message=msg, request_id=rid)


def capture_monitor(
    monitor_index: int = 1,
    out_path: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    """
    Снимок целого монитора через MSS (не только окна процесса).
    monitor_index: 0 — виртуальный «все мониторы», 1 — основной, далее — дополнительные.
    После отключения RDP без виртуального дисплея кадр часто чёрный — смотрите data.content_hint и README (RDS).
    """
    rid = parse_request_id(client_request_id)
    try:
        if sys.platform != "win32":
            return err_json("ERR_PLATFORM", "capture_monitor только на Windows", request_id=rid)
        import os
        import tempfile
        import uuid

        import mss

        if not out_path:
            out_path = os.path.join(tempfile.gettempdir(), f"lep_mcp_mon_{uuid.uuid4().hex}.png")
        with mss.mss() as sct:
            monitors = sct.monitors
            n_mon = len(monitors)
            if monitor_index < 0 or monitor_index >= n_mon:
                return err_json(
                    "ERR_VALIDATION",
                    f"monitor_index вне диапазона 0..{n_mon - 1}",
                    data={"monitors_count": n_mon},
                    request_id=rid,
                )
            region = monitors[monitor_index]
            shot = sct.grab(region)
        bbox = {
            "left": int(region["left"]),
            "top": int(region["top"]),
            "width": int(region["width"]),
            "height": int(region["height"]),
        }
        return _save_grab_png(
            shot,
            out_path,
            include_base64,
            max_edge_px,
            {
                "bbox": bbox,
                "monitor_index": monitor_index,
                "monitors_count": n_mon,
                "capture_message": "capture_monitor",
            },
            rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def capture_window(
    process_name: str | None = None,
    title_contains: str | None = None,
    out_path: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    rid = parse_request_id(client_request_id)
    try:
        if sys.platform != "win32":
            return err_json("ERR_PLATFORM", "capture_window только на Windows", request_id=rid)
        import os
        import tempfile
        import uuid

        import mss

        w = _resolve_top_window(process_name, title_contains)
        r = w.rectangle()
        bbox = {"left": int(r.left), "top": int(r.top), "width": int(r.width()), "height": int(r.height())}
        if not out_path:
            out_path = os.path.join(tempfile.gettempdir(), f"lep_mcp_cap_{uuid.uuid4().hex}.png")
        with mss.mss() as sct:
            shot = sct.grab(bbox)
        return _save_grab_png(
            shot,
            out_path,
            include_base64,
            max_edge_px,
            {"bbox": bbox, "capture_message": "capture_window"},
            rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)

"""UI Automation helpers (pywinauto). Windows only. Все ответы — JSON-конверт protocol."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

from src.protocol import err_json, ok_json, parse_request_id

# Меняйте при доработке модалок / send_keys — смотрите agent_session.uia_tools_revision.
UIA_TOOLS_REVISION = "2026-04-15-winforms-modal-v1"


def _modal_poll_sec() -> float:
    raw = (os.environ.get("MCP_MODAL_POLL_SEC") or "").strip()
    if raw:
        try:
            return max(0.03, min(float(raw), 2.0))
        except ValueError:
            pass
    return 0.12


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


def _find_uia_subtree_anchor(
    top: Any,
    anchor_automation_id: str | None,
    anchor_name_contains: str | None,
) -> tuple[Any | None, str]:
    """
    Ищет корень поддерева палитры LEP: сначала automation_id (WinForms Name),
    иначе regex по имени (заголовок «LEP — …» / «LEP - …» и т.п.).
    Если задан нестандартный anchor_automation_id и не найден — возврат (None, …) без regex.
    Для значения по умолчанию ``lep_palette_root`` при отсутствии узла выполняется fallback на regex.
    """
    aid = (anchor_automation_id or "").strip()
    if aid:
        matches = _descendants_matching(top, aid, None, None)
        if matches:
            return matches[0], f"automation_id:{aid}"
        if aid != "lep_palette_root":
            return None, f"automation_id_not_found:{aid}"
    nc = (anchor_name_contains or "").strip()
    if nc:
        try:
            pat = re.compile(nc, re.IGNORECASE)
        except re.error:
            pat = re.compile(re.escape(nc), re.IGNORECASE)
    else:
        pat = re.compile(
            r"(?i)(система\s+автоматизации|кабельн).{0,120}(lep|леп)|"
            r"(lep|леп).{0,120}(система|кабельн|автоматизац)|"
            r"^\s*lep\s*[-—]|lep_palette_root",
        )
    best: Any | None = None
    best_score = 0
    scanned = 0
    for el in top.descendants():
        scanned += 1
        if scanned > _MAX_DESC_SCAN:
            break
        try:
            info = el.element_info
            nm = (getattr(info, "name", None) or "").strip()
            if not nm or not pat.search(nm):
                continue
            r = el.rectangle()
            area = max(1, int(r.width()) * int(r.height()))
            ct = str(getattr(info, "control_type", "") or "")
            score = area
            if "Tab" in ct or "Pane" in ct:
                score += 8000
            if "Window" in ct:
                score += 4000
            if nm[:3].upper() == "LEP":
                score += 2000
            if score > best_score:
                best_score = score
                best = el
        except Exception:
            continue
    if best is None:
        return None, "not_found"
    return best, "name_regex"


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
    uia_list только по поддереву палитры LEP: якорь по automation_id (по умолчанию lep_palette_root)
    или по anchor_name_contains / встроенному regex по заголовку LEP.
    Не съедает max_nodes лентой/DataGrid верхнего окна nCAD.exe.
    """
    rid = parse_request_id(client_request_id)
    try:
        top = _resolve_top_window(process_name, title_contains)
        root, via = _find_uia_subtree_anchor(top, anchor_automation_id, anchor_name_contains)
        if root is None:
            return err_json(
                "ERR_NOT_FOUND",
                "Якорь поддерева LEP не найден (задайте anchor_name_contains или откройте палитру; "
                "в плагине должен быть Name=lep_palette_root на корневой панели).",
                data={"anchor_via": via, "hint": "fallback: uia_list(process_name=...) с большим max_nodes"},
                request_id=rid,
            )
        out: list[dict[str, Any]] = []
        truncated = [False]
        md = max(1, min(int(max_depth), 24))
        mn = max(10, min(int(max_nodes), 5000))
        _walk(root, 0, md, mn, out, truncated)
        try:
            rnm = (root.element_info.name or "")[:200]
        except Exception:
            rnm = ""
        return ok_json(
            data={
                "items": out,
                "count": len(out),
                "truncated": truncated[0],
                "limits": {"max_depth": md, "max_nodes": mn},
                "target": {
                    "process_name": process_name,
                    "title_contains": title_contains,
                    "anchor_via": via,
                    "anchor_name_preview": rnm,
                },
            },
            message="uia_list_subtree",
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
    r"Анализ трассы|Экспорт|Импорт|Корректировка|Журнал|LEP —|LEP -|"
    r"Профили пересечений|Построение трассы|"
    r"Совет дня|Совет|Tip of the Day|nanoCAD",
    re.IGNORECASE,
)


def uia_revision_payload() -> dict[str, str]:
    """Короткий снимок для agent_session: сверка с репо без чтения git."""
    import hashlib

    digest = hashlib.sha1(_DEFAULT_MODAL_TITLE_RE.pattern.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return {
        "uia_tools_revision": UIA_TOOLS_REVISION,
        "uia_modal_title_pattern_sha12": digest,
    }


def _win32_pid_for_process(proc_name: str | None) -> int:
    if not (proc_name or "").strip():
        return 0
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(path=proc_name.strip(), timeout=2)
        return int(app.process)
    except Exception:
        return 0


def _win32_hwnd_pid(hwnd: int) -> int:
    if not hwnd or sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(int(hwnd)), ctypes.byref(pid))
    return int(pid.value)


def _win32_get_owner_hwnd(hwnd: int) -> int:
    if not hwnd or sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    GW_OWNER = 4
    return int(user32.GetWindow(wintypes.HWND(int(hwnd)), GW_OWNER) or 0)


def _win32_modal_owned_by_ncad_tree(owner_hwnd: int, main_ncad_hwnd: int) -> bool:
    """Модалка LEP может иметь GW_OWNER = палитра (дочернее к главному окну), а не сам top-level nCAD."""
    if not owner_hwnd or not main_ncad_hwnd or sys.platform != "win32":
        return False
    if owner_hwnd == main_ncad_hwnd:
        return True
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    try:
        if user32.IsChild(wintypes.HWND(int(main_ncad_hwnd)), wintypes.HWND(int(owner_hwnd))):
            return True
    except Exception:
        pass
    h = int(owner_hwnd)
    for _ in range(8):
        o = _win32_get_owner_hwnd(h)
        if not o:
            break
        if o == main_ncad_hwnd:
            return True
        try:
            if user32.IsChild(wintypes.HWND(int(main_ncad_hwnd)), wintypes.HWND(int(o))):
                return True
        except Exception:
            pass
        h = o
    return False


def _win32_largest_visible_top_hwnd_for_pid(target_pid: int) -> int:
    """Главное окно процесса: самое большое видимое top-level без GW_OWNER."""
    if sys.platform != "win32" or target_pid <= 0:
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    GW_OWNER = 4
    best_hwnd = 0
    best_area = 0
    pid_out = wintypes.DWORD()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_top(hwnd: int, _lp: int) -> bool:
        nonlocal best_hwnd, best_area
        if not user32.IsWindowVisible(hwnd):
            return True
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if int(pid_out.value) != target_pid:
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        area = max(1, int(rect.right - rect.left) * int(rect.bottom - rect.top))
        if area > best_area:
            best_area = area
            best_hwnd = int(hwnd)
        return True

    user32.EnumWindows(enum_top, 0)
    return best_hwnd


def _win32_click_ok_in_children(hwnd_root: int, button_titles: list[str], max_depth: int = 10) -> tuple[bool, str]:
    """
    Рекурсивно ищет дочернее окно с текстом из button_titles (GetWindowTextW),
    класс содержит «button» — BM_CLICK.
    """
    if sys.platform != "win32":
        return False, "not_win32"
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    BM_CLICK = 0x00F5
    norms = [(b.strip().casefold(), b.strip()) for b in button_titles if (b or "").strip()]
    if not norms:
        norms = [("ok", "OK"), ("ок", "ОК")]
    seen: set[int] = set()

    def dfs(hwnd: int, depth: int) -> tuple[bool, str]:
        if hwnd in seen or depth > max_depth:
            return False, ""
        seen.add(hwnd)
        cls_buf = ctypes.create_unicode_buffer(260)
        user32.GetClassNameW(hwnd, cls_buf, 260)
        cn = (cls_buf.value or "").strip()
        tbuf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, tbuf, 512)
        text = (tbuf.value or "").strip()
        tl = text.casefold()
        if "button" in cn.lower() or cn.endswith("Button"):
            for norm, _orig in norms:
                if norm and (tl == norm or tl.startswith(norm) or norm in tl):
                    user32.SendMessageW(hwnd, BM_CLICK, 0, 0)
                    return True, f"child_BM_CLICK:{text!r}"
        kids: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def ec(ch: int, _lp2: int) -> bool:
            kids.append(int(ch))
            return True

        user32.EnumChildWindows(hwnd, ec, 0)
        for ch in kids:
            ok, det = dfs(ch, depth + 1)
            if ok:
                return True, det
        return False, ""

    ok, det = dfs(int(hwnd_root), 0)
    return ok, det


def _win32_try_modal_ok(
    pat: re.Pattern,
    max_window_width: int,
    max_window_height: int,
    button_titles: list[str],
    owner_process_name: str | None,
) -> tuple[bool, str, str, int, int, str, int, int]:
    """
    Фолбэк, если UIA не видит кнопку: #32770, owned от nCAD, GetDlgItem(IDOK), дочерние Button, WM_COMMAND.
    Возвращает (ok, title, class_name, rw, rh, detail, hwnd, owner_hwnd).
    """
    if sys.platform != "win32":
        return False, "", "", 0, 0, "not_win32", 0, 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    BM_CLICK = 0x00F5
    IDOK = 1
    WM_COMMAND = 0x0111
    GW_OWNER = 4
    main_hwnd = _win32_largest_visible_top_hwnd_for_pid(_win32_pid_for_process(owner_process_name))
    matches: list[tuple[int, str, str, int, int, bool, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        cls_buf = ctypes.create_unicode_buffer(260)
        user32.GetClassNameW(hwnd, cls_buf, 260)
        cn = (cls_buf.value or "").strip()
        is_dialog_shell = "#32770" in cn or "dialog" in cn.lower()
        if not is_dialog_shell:
            return True
        title_buf = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(hwnd, title_buf, 1024)
        title = (title_buf.value or "").strip()
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        rw = int(rect.right - rect.left)
        rh = int(rect.bottom - rect.top)
        if rw > int(max_window_width) or rh > int(max_window_height):
            return True
        title_hit = bool(pat.search(title)) if title else False
        small_dialog = is_dialog_shell and rw < 900 and rh < 700
        if not title_hit and not small_dialog:
            return True
        owner = int(user32.GetWindow(hwnd, GW_OWNER) or 0)
        pri = 0
        if main_hwnd and owner == main_hwnd:
            pri = 3
        elif owner:
            pri = 1
        if title_hit:
            pri += 2
        matches.append((hwnd, title, cn, rw, rh, title_hit, pri))
        return True

    user32.EnumWindows(enum_proc, 0)
    matches.sort(key=lambda t: (-t[6], not t[5], -t[3] * t[4]))
    for hwnd, title, cn, rw, rh, th, _pri in matches:
        owner_hwnd = int(user32.GetWindow(hwnd, GW_OWNER) or 0)
        ok_child = user32.GetDlgItem(hwnd, IDOK)
        if ok_child:
            user32.SendMessageW(ok_child, BM_CLICK, 0, 0)
            return True, title, cn, rw, rh, "win32_GetDlgItem_BM_CLICK", int(hwnd), owner_hwnd
        ok2, det2 = _win32_click_ok_in_children(int(hwnd), button_titles)
        if ok2:
            return True, title, cn, rw, rh, det2, int(hwnd), owner_hwnd
        if th:
            user32.SendMessageW(hwnd, WM_COMMAND, wintypes.WPARAM(IDOK), 0)
            return True, title, cn, rw, rh, "win32_WM_COMMAND_IDOK", int(hwnd), owner_hwnd
    return False, "", "", 0, 0, "win32_no_match", 0, 0


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
    main_hwnd_ncad: int = 0,
) -> tuple[bool, str, str, int, int, bool]:
    """(ok, title, class_name, rw, rh, title_hit) для верхнего уровня."""
    try:
        if not w.is_visible():
            return False, "", "", 0, 0, False
    except Exception:
        return False, "", "", 0, 0, False
    try:
        r = w.rectangle()
        rw, rh = int(r.width()), int(r.height())
    except Exception:
        return False, "", "", 0, 0, False
    if rw > int(max_window_width) or rh > int(max_window_height):
        return False, "", "", rw, rh, False
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

    hwnd_u = _hwnd_uia(w)
    owner_hwnd = _win32_get_owner_hwnd(hwnd_u) if hwnd_u else 0
    cls_lower = cls.lower()
    is_winforms = "windowsforms" in cls_lower and "window" in cls_lower
    winforms_owned = bool(
        is_winforms
        and main_hwnd_ncad
        and owner_hwnd
        and _win32_modal_owned_by_ncad_tree(owner_hwnd, main_hwnd_ncad)
        and rw >= 100
        and rh >= 60
    )

    if title_hit or small_dialog or winforms_owned:
        return True, title, cls, rw, rh, title_hit
    return False, title, cls, rw, rh, title_hit


def _uia_try_click_modal_button(w: Any, button_titles: list[str]) -> tuple[bool, str, str]:
    """
    Закрыть модалку кликом по кнопке OK/ОК: прямой child_window, затем обход descendants,
    затем AcceptButton через {ENTER}. Возвращает (ok, button_label, via).
    """
    for bt in button_titles:
        try:
            ch = w.child_window(title=bt, control_type="Button")
            if ch.exists(timeout=0.15):
                ch.click_input()
                return True, bt, "uia_Button_click"
        except Exception:
            continue
    norms = [(b.strip().casefold(), b.strip()) for b in button_titles if (b or "").strip()]
    try:
        desc = w.descendants(control_type="Button")
    except Exception:
        desc = []
    for el in desc:
        try:
            wt = (el.window_text() or "").strip()
            name = ""
            try:
                name = (el.element_info.name or "").strip()
            except Exception:
                pass
            wtf = wt.casefold()
            nf = name.casefold()
            for norm, orig in norms:
                if not norm:
                    continue
                if wtf == norm or nf == norm or wtf.startswith(norm) or nf.startswith(norm):
                    el.click_input()
                    return True, orig, "uia_Button_descendant"
        except Exception:
            continue
    try:
        desc2 = list(w.descendants(control_type="Button"))
    except Exception:
        desc2 = []
    if desc2 and len(desc2) <= 6:
        try:
            w.set_focus()
            time.sleep(0.04)
            w.type_keys("{ENTER}")
            return True, "{ENTER}", "acceptbutton_enter"
        except Exception:
            pass
    return False, "", ""


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
    Закрыть типичный MessageBox Win32 / модалку поверх nanoCAD: обход **top-level** окон Desktop (UIA),
    а не только потомков nCAD.exe — там кнопка OK часто не находится через uia_click(process_name=...).

    - title_regex: если задан — заголовок окна должен совпадать с regex; иначе используется встроенный
      список типичных заголовков LEP / системных диалогов.
    - button_titles: через запятую подписи кнопок в порядке попытки (по умолчанию OK, ОК).
    - max_window_width/height: отсекаем главное окно nanoCAD (большое); модалки обычно меньше.
    - owner_process_name: для Win32-фолбэка — PID процесса-владельца (приоритет owned-модалок nCAD); пусто — не поднимать приоритет.
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

    main_ncad = 0
    if (owner_process_name or "").strip():
        main_ncad = _win32_largest_visible_top_hwnd_for_pid(_win32_pid_for_process(owner_process_name))
    poll = _modal_poll_sec()
    d = Desktop(backend="uia")
    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    last_err = ""
    while time.monotonic() < deadline:
        try:
            ranked: list[tuple[int, Any, str, str, int, int, bool]] = []
            for w in d.windows():
                try:
                    if not w.is_visible():
                        continue
                except Exception:
                    continue
                ok_c, title, cls, rw, rh, th = _modal_candidate_match(
                    w, pat, max_window_width, max_window_height, main_ncad
                )
                if not ok_c:
                    continue
                hwnd_u = _hwnd_uia(w)
                oh = _win32_get_owner_hwnd(hwnd_u) if hwnd_u else 0
                pri = 0
                if main_ncad and oh and _win32_modal_owned_by_ncad_tree(oh, main_ncad):
                    pri += 8
                if th:
                    pri += 4
                if "#32770" in (cls or ""):
                    pri += 2
                if "windowsforms" in (cls or "").lower():
                    pri += 1
                ranked.append((pri, w, title, cls, rw, rh, th))
            for _pri, w, title, cls, rw, rh, _th in sorted(ranked, key=lambda t: -t[0]):
                ok_btn, btn_lbl, via = _uia_try_click_modal_button(w, buttons)
                if ok_btn:
                    wh = _hwnd_uia(w)
                    return ok_json(
                        data={
                            "closed": True,
                            "window_title": title,
                            "class_name": cls,
                            "button": btn_lbl,
                            "size": {"w": rw, "h": rh},
                            "via": via,
                            "hwnd": wh,
                        },
                        message="uia_modal_ok",
                        request_id=rid,
                    )
        except Exception as e:
            last_err = str(e)
        time.sleep(poll)
    ok_w, t_w, c_w, rw_w, rh_w, detail_w, dlg_hwnd, own_hwnd = _win32_try_modal_ok(
        pat, max_window_width, max_window_height, buttons, owner_process_name
    )
    if ok_w:
        return ok_json(
            data={
                "closed": True,
                "window_title": t_w,
                "class_name": c_w,
                "button": "OK(win32)",
                "size": {"w": rw_w, "h": rh_w},
                "via": detail_w,
                "hwnd": dlg_hwnd,
                "owner_hwnd": own_hwnd,
            },
            message="uia_modal_ok",
            request_id=rid,
        )
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

    main_ncad = _win32_largest_visible_top_hwnd_for_pid(_win32_pid_for_process("nCAD.exe"))
    poll = _modal_poll_sec()
    d = Desktop(backend="uia")
    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    last_err = ""
    while time.monotonic() < deadline:
        try:
            ranked: list[tuple[int, Any, str, str, int, int]] = []
            for w in d.windows():
                try:
                    if not w.is_visible():
                        continue
                except Exception:
                    continue
                ok_c, title, cls, rw, rh, th = _modal_candidate_match(
                    w, pat, max_window_width, max_window_height, main_ncad
                )
                if not ok_c:
                    continue
                hwnd_u = _hwnd_uia(w)
                oh = _win32_get_owner_hwnd(hwnd_u) if hwnd_u else 0
                pri = 0
                if main_ncad and oh and _win32_modal_owned_by_ncad_tree(oh, main_ncad):
                    pri += 8
                if th:
                    pri += 4
                if "#32770" in (cls or ""):
                    pri += 2
                if "windowsforms" in (cls or "").lower():
                    pri += 1
                ranked.append((pri, w, title, cls, rw, rh))
            for _pri, w, title, cls, rw, rh in sorted(ranked, key=lambda t: -t[0]):
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
        time.sleep(poll)
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


def mouse_click_window(
    client_x: int,
    client_y: int,
    process_name: str | None = None,
    title_contains: str | None = None,
    button: str = "left",
    double: bool = False,
    client_request_id: str | None = None,
) -> str:
    """
    Клик в **клиентских** координатах целевого окна: перевод в экран через ClientToScreen
    (меньше ошибок DPI/смещения, чем ручной пересчёт от bbox скриншота).
    """
    rid = parse_request_id(client_request_id)
    _require_win()
    import ctypes
    from ctypes import wintypes

    from pywinauto import mouse

    try:
        cx = int(client_x)
        cy = int(client_y)
    except (TypeError, ValueError):
        return err_json("ERR_VALIDATION", "client_x и client_y должны быть целыми", request_id=rid)
    btn = (button or "left").lower().strip()
    if btn not in ("left", "right", "middle"):
        return err_json("ERR_VALIDATION", "button: left | right | middle", request_id=rid)
    try:
        w = _resolve_top_window(process_name, title_contains)
        hwnd = _hwnd_uia(w)
        if not hwnd:
            return err_json("ERR_UIA", "Не удалось получить HWND окна для ClientToScreen", request_id=rid)
        pt = wintypes.POINT(cx, cy)
        if not ctypes.windll.user32.ClientToScreen(int(hwnd), ctypes.byref(pt)):
            return err_json("ERR_UIA", "ClientToScreen вернул 0", request_id=rid)
        sx, sy = int(pt.x), int(pt.y)
        if double:
            mouse.double_click(button=btn, coords=(sx, sy))
        else:
            mouse.click(button=btn, coords=(sx, sy))
        return ok_json(
            data={
                "clicked": True,
                "client_x": cx,
                "client_y": cy,
                "screen_x": sx,
                "screen_y": sy,
                "button": btn,
                "double": bool(double),
                "hwnd": int(hwnd),
            },
            message="mouse_click_window",
            request_id=rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def mouse_move(
    screen_x: int,
    screen_y: int,
    client_request_id: str | None = None,
) -> str:
    """
    Переместить курсор в экранные координаты **без клика** (видно при наблюдении за RDP).
    """
    rid = parse_request_id(client_request_id)
    _require_win()
    from pywinauto import mouse

    try:
        x = int(screen_x)
        y = int(screen_y)
    except (TypeError, ValueError):
        return err_json("ERR_VALIDATION", "screen_x и screen_y должны быть целыми", request_id=rid)
    try:
        mouse.move(coords=(x, y))
        return ok_json(
            data={"moved": True, "screen_x": x, "screen_y": y},
            message="mouse_move",
            request_id=rid,
        )
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)


def mouse_move_smooth(
    screen_x: int,
    screen_y: int,
    steps: int = 28,
    pause_ms: float = 18.0,
    client_request_id: str | None = None,
) -> str:
    """
    Плавно вести курсор по прямой от **текущей** позиции к (screen_x, screen_y).
    Удобно для демонстрации на удалённом столе: между шагами короткая пауза.
    steps: число отрезков (2–120); pause_ms: задержка между шагами, мс (1–400).
    """
    rid = parse_request_id(client_request_id)
    _require_win()
    import win32api
    from pywinauto import mouse

    try:
        x = int(screen_x)
        y = int(screen_y)
        n = int(steps)
        pause = float(pause_ms)
    except (TypeError, ValueError):
        return err_json("ERR_VALIDATION", "некорректные числовые параметры", request_id=rid)
    if n < 2:
        n = 2
    if n > 120:
        n = 120
    if pause < 1.0:
        pause = 1.0
    if pause > 400.0:
        pause = 400.0
    try:
        cx, cy = win32api.GetCursorPos()
    except Exception as e:
        return err_json("ERR_UIA", f"GetCursorPos: {e}", request_id=rid)
    try:
        for i in range(1, n + 1):
            t = i / float(n)
            nx = int(round(cx + (x - cx) * t))
            ny = int(round(cy + (y - cy) * t))
            mouse.move(coords=(nx, ny))
            time.sleep(pause / 1000.0)
        return ok_json(
            data={
                "moved": True,
                "screen_x": x,
                "screen_y": y,
                "from_x": cx,
                "from_y": cy,
                "steps": n,
                "pause_ms": pause,
            },
            message="mouse_move_smooth",
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
        _require_win()
        import ctypes
        from ctypes import wintypes

        from pywinauto import Desktop

        user32 = ctypes.windll.user32
        fg = int(user32.GetForegroundWindow() or 0)
        if fg:
            try:
                d = Desktop(backend="uia")
                fw = d.window(handle=fg)
                fw.wait("exists", timeout=0.35)
                cls = ""
                try:
                    cls = (fw.class_name() or "").strip()
                except Exception:
                    pass
                try:
                    r = fw.rectangle()
                    rw, rh = int(r.width()), int(r.height())
                except Exception:
                    rw, rh = 9999, 9999
                ct = ""
                try:
                    ct = str(fw.element_info.control_type or "")
                except Exception:
                    pass
                is_modal_shell = "#32770" in cls or "Dialog" in ct
                max_mw = int(os.environ.get("MCP_SENDKEYS_MODAL_MAX_W", "1400"))
                max_mh = int(os.environ.get("MCP_SENDKEYS_MODAL_MAX_H", "950"))
                if is_modal_shell and rw < max_mw and rh < max_mh:
                    try:
                        user32.SetForegroundWindow(fg)
                    except Exception:
                        pass
                    fw.set_focus()
                    if text:
                        fw.type_keys(text, with_spaces=True)
                    if with_enter:
                        fw.type_keys("{ENTER}")
                    return ok_json(
                        data={
                            "sent": True,
                            "with_enter": with_enter,
                            "via": "foreground_modal",
                            "hwnd": fg,
                            "class_name": cls,
                            "size": {"w": rw, "h": rh},
                        },
                        message="send_keys",
                        request_id=rid,
                    )
                ncad_pid = _win32_pid_for_process("nCAD.exe")
                if ncad_pid and _win32_hwnd_pid(fg) == ncad_pid:
                    cls_lower = (cls or "").lower()
                    is_winforms = "windowsforms" in cls_lower and "window" in cls_lower
                    if (
                        is_winforms
                        and rw < max_mw
                        and rh < max_mh
                        and rw >= 100
                        and rh >= 60
                    ):
                        try:
                            user32.SetForegroundWindow(fg)
                        except Exception:
                            pass
                        fw.set_focus()
                        if text:
                            fw.type_keys(text, with_spaces=True)
                        if with_enter:
                            fw.type_keys("{ENTER}")
                        return ok_json(
                            data={
                                "sent": True,
                                "with_enter": with_enter,
                                "via": "foreground_winforms_modal",
                                "hwnd": fg,
                                "class_name": cls,
                                "size": {"w": rw, "h": rh},
                            },
                            message="send_keys",
                            request_id=rid,
                        )
            except Exception:
                pass
        w = _resolve_top_window(process_name, title_contains)
        try:
            hwnd = _hwnd_uia(w)
            if hwnd:
                user32.SetForegroundWindow(int(hwnd))
        except Exception:
            pass
        w.set_focus()
        if text:
            w.type_keys(text, with_spaces=True)
        if with_enter:
            w.type_keys("{ENTER}")
        return ok_json(data={"sent": True, "with_enter": with_enter, "via": "target_window"}, message="send_keys", request_id=rid)
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


def _filename_slug_segment(raw: str, max_len: int = 96) -> str:
    """Фрагмент имени PNG: латиница, цифры, ._- ; пробелы → _."""
    s = (raw or "").strip().lower()
    out: list[str] = []
    prev_us = False
    for ch in s:
        if ord(ch) < 128 and (ch.isalnum() or ch in "-_."):
            out.append(ch)
            prev_us = False
        elif ch.isspace():
            if not prev_us:
                out.append("_")
                prev_us = True
    slug = "".join(out).strip("._") or "snap"
    return slug[:max_len]


def _resolve_png_out_path(
    out_path: str | None,
    filename_suffix: str | None,
    *,
    default_prefix: str,
) -> str:
    """Полный путь для PNG: явный out_path или каталог MCP_CAPTURE_DIR/temp + префикс + slug + uuid."""
    import os
    import tempfile
    import uuid

    if (out_path or "").strip():
        return str(out_path).strip()
    capture_dir = (os.environ.get("MCP_CAPTURE_DIR") or "").strip()
    if not capture_dir:
        capture_dir = tempfile.gettempdir()
    os.makedirs(capture_dir, exist_ok=True)
    slug = _filename_slug_segment(filename_suffix) if (filename_suffix or "").strip() else ""
    if slug:
        fname = f"{default_prefix}_{slug}_{uuid.uuid4().hex[:8]}.png"
    else:
        fname = f"{default_prefix}_{uuid.uuid4().hex}.png"
    return os.path.join(capture_dir, fname)


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
    filename_suffix: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    """
    Снимок целого монитора через MSS (не только окна процесса).
    monitor_index: 0 — виртуальный «все мониторы», 1 — основной, далее — дополнительные.
    filename_suffix: если out_path не задан — фрагмент имени файла (латиница); каталог — MCP_CAPTURE_DIR или temp.
    После отключения RDP без виртуального дисплея кадр часто чёрный — смотрите data.content_hint и README (RDS).
    """
    rid = parse_request_id(client_request_id)
    try:
        if sys.platform != "win32":
            return err_json("ERR_PLATFORM", "capture_monitor только на Windows", request_id=rid)
        import mss

        explicit_mon = (filename_suffix or "").strip()
        slug_used = _filename_slug_segment(explicit_mon) if explicit_mon else None
        out_path = _resolve_png_out_path(out_path, explicit_mon or None, default_prefix="lep_mcp_mon")
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
                "filename_suffix": explicit_mon or None,
                "filename_slug_used": slug_used,
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
    filename_suffix: str | None = None,
    include_base64: bool = True,
    max_edge_px: int = 2400,
    client_request_id: str | None = None,
) -> str:
    rid = parse_request_id(client_request_id)
    try:
        if sys.platform != "win32":
            return err_json("ERR_PLATFORM", "capture_window только на Windows", request_id=rid)
        import mss

        w = _resolve_top_window(process_name, title_contains)
        r = w.rectangle()
        bbox = {"left": int(r.left), "top": int(r.top), "width": int(r.width()), "height": int(r.height())}
        explicit_suffix = (filename_suffix or "").strip()
        auto_suffix = explicit_suffix
        if not auto_suffix:
            try:
                tw = (w.window_text() or "").strip()
                if tw:
                    auto_suffix = _filename_slug_segment(tw, max_len=48)
            except Exception:
                pass
        out_path = _resolve_png_out_path(
            out_path,
            auto_suffix or None,
            default_prefix="lep_mcp_cap",
        )
        with mss.mss() as sct:
            shot = sct.grab(bbox)
        return _save_grab_png(
            shot,
            out_path,
            include_base64,
            max_edge_px,
            {
                "bbox": bbox,
                "filename_suffix": explicit_suffix or None,
                "filename_slug_used": auto_suffix or None,
                "capture_message": "capture_window",
            },
            rid,
        )
    except ValueError as e:
        return err_json("ERR_VALIDATION", str(e), request_id=rid)
    except Exception as e:
        return err_json("ERR_UIA", str(e), request_id=rid)

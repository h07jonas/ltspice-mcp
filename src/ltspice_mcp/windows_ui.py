"""Windows equivalents of the macOS-only LTspice UI/window-automation helpers.

This module is imported lazily and only on ``platform.system() == "Windows"``.
It relies on ``pywin32`` for window discovery/automation, ``uiautomation``
(a pure-Python wrapper over Win32 UI Automation, via ``comtypes``) for
reading window text via a UI-Automation-tree walk, and ``Pillow`` (and
optionally ``mss``) for screenshot capture/processing. Those packages are
declared as ``sys_platform == "win32"`` extras in ``pyproject.toml`` so they
are not required on macOS/Linux.

Scope: this replicates what the macOS Accessibility/AppleScript/
ScreenCaptureKit helpers in ``ltspice.py`` do for LTspice specifically
(find its window(s), close them, read visible text, capture a screenshot of
just that window). It is not a general UI-automation framework.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

_LTSPICE_PROCESS_NAMES = {"ltspice.exe", "xviix64.exe", "scad3.exe", "xvii.exe"}

# WM_CLOSE / WM_GETTEXT / WM_GETTEXTLENGTH constants (avoid importing win32con
# eagerly at module import time in case pywin32 is unavailable).
WM_CLOSE = 0x0010
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E


class WindowsAutomationUnavailable(RuntimeError):
    """Raised when pywin32 (or another required Windows dependency) is missing."""


def _require_pywin32():
    try:
        import win32con  # noqa: F401
        import win32gui
        import win32process
    except ImportError as exc:  # pragma: no cover - exercised only without pywin32
        raise WindowsAutomationUnavailable(
            "pywin32 is required for LTspice UI automation on Windows. "
            "Install it with: pip install pywin32"
        ) from exc
    return win32gui, win32process


def is_ltspice_ui_running() -> bool:
    """Check whether an LTspice process is running, via `tasklist`."""
    try:
        for name in ("LTspice.exe", "XVIIx64.exe", "scad3.exe"):
            proc = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if name in proc.stdout:
                return True
    except Exception:
        return False
    return False


def open_in_ltspice_ui(
    target: Path,
    *,
    executable: Path | None = None,
    background: bool = True,
) -> dict[str, Any]:
    """Launch LTspice.exe (or the resolved executable) on `target`."""
    if executable is None:
        from .ltspice import find_ltspice_executable

        executable = find_ltspice_executable()
    if executable is None:
        return {
            "opened": False,
            "return_code": 1,
            "path": str(target),
            "background_requested": background,
            "background": background,
            "command": None,
            "stdout": "",
            "stderr": "Could not locate an LTspice executable on this machine.",
        }
    command = [str(executable), str(target)]
    try:
        creationflags = 0
        if background:
            # DETACHED_PROCESS / no console window flags aren't relevant for a
            # GUI app, but CREATE_NEW_PROCESS_GROUP avoids tying its lifetime
            # (Ctrl+C signals) to this process.
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        opened = True
        stderr = ""
    except Exception as exc:  # noqa: BLE001
        opened = False
        stderr = str(exc)
    return {
        "opened": opened,
        "return_code": 0 if opened else 1,
        "path": str(target),
        "background_requested": background,
        "background": background,
        "command": command,
        "stdout": "",
        "stderr": stderr,
    }


def _window_matches(
    win32gui,
    win32process,
    hwnd: int,
    *,
    title_contains: str,
    title_exact: str,
    window_id: int | None,
) -> bool:
    if not win32gui.IsWindowVisible(hwnd):
        return False
    if window_id is not None and hwnd == window_id:
        return True
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        import psutil  # optional; fall back to title-only matching if absent

        try:
            proc_name = psutil.Process(pid).name().lower()
            if proc_name not in _LTSPICE_PROCESS_NAMES:
                return False
        except Exception:
            pass
    except Exception:
        pass
    title = win32gui.GetWindowText(hwnd)
    if title_exact:
        return title == title_exact
    if title_contains:
        return title_contains.lower() in title.lower()
    return "ltspice" in title.lower()


def find_ltspice_windows(
    *,
    title_hint: str = "",
    exact_title: str | None = None,
    window_id: int | None = None,
) -> list[dict[str, Any]]:
    """Enumerate visible top-level windows matching the given selectors."""
    win32gui, win32process = _require_pywin32()
    title_contains = (title_hint or "").strip()
    title_exact = (exact_title or "").strip()
    matches: list[dict[str, Any]] = []

    def _callback(hwnd: int, _extra: Any) -> None:
        if _window_matches(
            win32gui,
            win32process,
            hwnd,
            title_contains=title_contains,
            title_exact=title_exact,
            window_id=window_id,
        ):
            matches.append({"hwnd": hwnd, "title": win32gui.GetWindowText(hwnd)})

    win32gui.EnumWindows(_callback, None)
    return matches


def close_ltspice_window(
    *,
    title_hint: str,
    exact_title: str | None = None,
    window_id: int | None = None,
    attempts: int = 1,
    retry_delay: float = 0.15,
) -> dict[str, Any]:
    """Close matching LTspice window(s) by posting WM_CLOSE to each handle."""
    win32gui, _win32process = _require_pywin32()
    max_attempts = max(1, min(10, int(attempts)))
    attempt_delay = max(0.0, float(retry_delay))
    attempt_events: list[dict[str, Any]] = []

    for attempt_index in range(max_attempts):
        matches = find_ltspice_windows(
            title_hint=title_hint, exact_title=exact_title, window_id=window_id
        )
        closed_count = 0
        for match in matches:
            try:
                win32gui.PostMessage(match["hwnd"], WM_CLOSE, 0, 0)
                closed_count += 1
            except Exception:  # noqa: BLE001
                continue
        if attempt_delay > 0:
            time.sleep(attempt_delay)
        remaining = find_ltspice_windows(
            title_hint=title_hint, exact_title=exact_title, window_id=window_id
        )
        matched_windows = len(matches)
        actually_closed = matched_windows - len(remaining)
        event = {
            "closed": matched_windows > 0 and len(remaining) == 0,
            "partially_closed": 0 < actually_closed < matched_windows,
            "matched_windows": matched_windows,
            "closed_windows": max(0, actually_closed),
            "remaining_windows": len(remaining),
            "close_strategy": "win32_wm_close",
            "status": "OK" if matched_windows > 0 else "NO_MATCHING_WINDOW",
            "return_code": 0,
            "title_hint": title_hint,
            "exact_title": exact_title,
            "window_id": window_id,
            "attempt": attempt_index + 1,
        }
        attempt_events.append(event)
        if event["closed"] or matched_windows == 0:
            break

    result = attempt_events[-1]
    result["attempt_count"] = len(attempt_events)
    if len(attempt_events) > 1:
        result["attempts"] = attempt_events
    return result


_UIA_MAX_DEPTH = 24
_UIA_MAX_NODES = 5000


def _collect_wm_gettext_chunks(win32gui, hwnd: int) -> list[str]:
    """Win32 WM_GETTEXT fallback: own window title plus direct child
    edit/static control text. This only sees real child HWNDs, so it misses
    anything exposed purely through UI Automation/MSAA (toolbar button
    names, menu items, status bar text, owner-drawn dialog controls, etc.)."""
    collected: list[str] = []

    def _collect(child_hwnd: int, _extra: Any) -> None:
        try:
            length = win32gui.SendMessage(child_hwnd, WM_GETTEXTLENGTH, 0, 0)
            if length > 0:
                text = win32gui.GetWindowText(child_hwnd)
                if text:
                    collected.append(text)
        except Exception:  # noqa: BLE001
            pass

    own_text = win32gui.GetWindowText(hwnd)
    if own_text:
        collected.append(own_text)
    try:
        win32gui.EnumChildWindows(hwnd, _collect, None)
    except Exception:  # noqa: BLE001
        pass
    return collected


def _collect_window_text_uia(hwnd: int) -> list[str]:
    """Walk the UI Automation tree rooted at `hwnd`, collecting Name/Value/
    description text from every element, breadth-first. Mirrors the macOS
    Accessibility-API walk in `ltspice.py`'s `_AX_TEXT_HELPER_SOURCE`
    (`collectWindowText`): same bounded depth/node count, same dedup
    strategy, so callers get comparable coverage on both platforms.

    Classic MFC/Win32 controls (toolbar buttons, menu items, status bar
    panes, dialog controls) are exposed to UI Automation via the built-in
    MSAA-to-UIA bridge, so this reaches much more than WM_GETTEXT does.
    A single owner-drawn/custom-painted control (e.g. LTspice's schematic
    canvas) still exposes no children or name/value through UIA - there is
    no text for us to read there on any platform, since it is pixels, not
    Windows/Accessibility API structured elements.
    """
    import uiautomation as auto

    root = auto.ControlFromHandle(hwnd)
    if root is None:
        return []

    chunks: list[str] = []
    seen_runtime_ids: set[tuple] = set()
    queue: list[tuple[Any, int]] = [(root, 0)]
    nodes_visited = 0

    while queue and nodes_visited < _UIA_MAX_NODES:
        control, depth = queue.pop(0)
        nodes_visited += 1

        try:
            runtime_id = tuple(control.GetRuntimeId())
        except Exception:  # noqa: BLE001
            runtime_id = None
        if runtime_id is not None:
            if runtime_id in seen_runtime_ids:
                continue
            seen_runtime_ids.add(runtime_id)

        try:
            name = control.Name
        except Exception:  # noqa: BLE001
            name = ""
        if name:
            chunks.append(name)

        try:
            value_pattern = control.GetValuePattern()
            if value_pattern:
                value = value_pattern.Value
                if value:
                    chunks.append(value)
        except Exception:  # noqa: BLE001
            pass

        try:
            legacy_pattern = control.GetLegacyIAccessiblePattern()
            if legacy_pattern:
                legacy_value = legacy_pattern.Value
                if legacy_value:
                    chunks.append(legacy_value)
                legacy_description = legacy_pattern.Description
                if legacy_description:
                    chunks.append(legacy_description)
        except Exception:  # noqa: BLE001
            pass

        if depth >= _UIA_MAX_DEPTH:
            continue
        try:
            child = control.GetFirstChildControl()
            while child:
                queue.append((child, depth + 1))
                child = child.GetNextSiblingControl()
        except Exception:  # noqa: BLE001
            pass

    return chunks


def _select_best_text(chunks: list[str], max_chars: int) -> str:
    """Dedup, prefer .meas/measurement chunks, join, truncate. Mirrors the
    macOS helper's `selectBestText` so both platforms rank/trim text the
    same way."""
    ordered: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        cleaned = chunk.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)

    if not ordered:
        return ""

    measurement_chunks = [
        c for c in ordered if "measurement:" in c.lower() or ".meas" in c.lower()
    ]
    selected = measurement_chunks if measurement_chunks else ordered
    combined = "\n".join(selected)
    if len(combined) > max_chars:
        return combined[:max_chars]
    return combined


def read_ltspice_window_text(
    *,
    title_hint: str = "",
    exact_title: str | None = None,
    window_id: int | None = None,
    max_chars: int = 200000,
) -> dict[str, Any]:
    """Read text from a matching LTspice window.

    Primary path: walk the window's UI Automation tree (via the
    `uiautomation` package, which wraps Win32 UI Automation and its
    built-in MSAA bridge) and collect Name/Value/description text from
    every element - toolbar buttons, menu items, status bar text, dialog
    controls, log viewers, etc. This is the Windows analogue of the macOS
    Accessibility-API tree walk in `ltspice.py`.

    Fallback: if UIA is unavailable or yields nothing, fall back to the
    older WM_GETTEXT-only approach (own window title plus direct child
    edit/static control text) so a missing/broken `uiautomation` install
    doesn't regress the previously working case.

    Known gap shared with the macOS path: LTspice's schematic canvas is a
    single owner-drawn/custom-painted control. Neither UI Automation nor
    the macOS Accessibility API can see component labels, wire routing, or
    other schematic content painted directly by LTspice - there is no
    accessible-tree representation of it on either platform, so this
    cannot return schematic-canvas text no matter which backend is used.
    """
    win32gui, _win32process = _require_pywin32()
    safe_max_chars = max(512, min(2_000_000, int(max_chars)))
    matches = find_ltspice_windows(
        title_hint=title_hint, exact_title=exact_title, window_id=window_id
    )
    if not matches:
        return {
            "ok": False,
            "status": "NO_MATCHING_WINDOW",
            "error": "No matching LTspice window found.",
            "text": "",
            "matched_windows": 0,
        }

    hwnd = matches[0]["hwnd"]

    uia_error: str | None = None
    uia_chunks: list[str] = []
    try:
        uia_chunks = _collect_window_text_uia(hwnd)
    except ImportError as exc:
        uia_error = f"uiautomation package unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001
        uia_error = str(exc)

    backend = "uia_tree_walk"
    text_value = _select_best_text(uia_chunks, safe_max_chars)
    chunk_count = len(uia_chunks)

    if not text_value:
        # Fall back to WM_GETTEXT (own title + direct child edit/static
        # controls) if UIA raised, or simply found no text.
        backend = "wm_gettext_fallback"
        fallback_chunks = _collect_wm_gettext_chunks(win32gui, hwnd)
        text_value = "\n".join(dict.fromkeys(c.strip() for c in fallback_chunks if c.strip()))
        if len(text_value) > safe_max_chars:
            text_value = text_value[:safe_max_chars]
        chunk_count = len(fallback_chunks)

    return {
        "ok": bool(text_value),
        "status": "OK" if text_value else "NO_TEXT_FOUND",
        "text": text_value,
        "text_length": len(text_value),
        "matched_windows": len(matches),
        "window_title": matches[0]["title"],
        "window_id": hwnd,
        "chunk_count": chunk_count,
        "backend": backend,
        "uia_error": uia_error,
        "title_hint": title_hint,
        "exact_title": exact_title,
        "max_chars": safe_max_chars,
    }


def capture_window(hwnd: int, output_path: Path) -> dict[str, Any]:
    """Capture a single window to a PNG file via PrintWindow, falling back to
    a full-screen `mss` grab of the window's bounding rect if that yields a
    blank image (common for some GPU-accelerated/legacy-GDI windows)."""
    win32gui, _win32process = _require_pywin32()
    try:
        import win32ui
        import win32con
        from PIL import Image
    except ImportError as exc:
        raise WindowsAutomationUnavailable(
            "pywin32 (win32ui) and Pillow are required for window capture on Windows. "
            "Install them with: pip install pywin32 Pillow"
        ) from exc

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Window {hwnd} has an invalid bounding rect: {(left, top, right, bottom)}")

    import ctypes

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)

    # PW_RENDERFULLCONTENT (3) captures modern/DirectX-composited windows correctly.
    # pywin32's win32gui does not wrap PrintWindow, so call user32 directly.
    result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

    bmp_info = bitmap.GetInfo()
    bmp_bits = bitmap.GetBitmapBits(True)
    image = Image.frombuffer(
        "RGB",
        (bmp_info["bmWidth"], bmp_info["bmHeight"]),
        bmp_bits,
        "raw",
        "BGRX",
        0,
        1,
    )

    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    used_fallback = False
    if result != 1 or image.getbbox() is None:
        # PrintWindow failed or produced a blank image; fall back to a
        # region grab of the window's screen rect via mss.
        used_fallback = True
        try:
            import mss

            with mss.mss() as sct:
                region = {"left": left, "top": top, "width": width, "height": height}
                shot = sct.grab(region)
                image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except ImportError as exc:
            raise WindowsAutomationUnavailable(
                "PrintWindow capture failed and the `mss` fallback is not installed. "
                "Install it with: pip install mss"
            ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output_path), format="PNG")
    return {
        "captured": True,
        "backend": "mss_fallback" if used_fallback else "print_window",
        "hwnd": hwnd,
        "width": image.width,
        "height": image.height,
        "output_path": str(output_path),
    }


def downscale_image_file(path: Path, downscale_factor: float) -> dict[str, Any]:
    """Resize a PNG in place using Pillow."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise WindowsAutomationUnavailable(
            "Pillow is required to downscale images on Windows. Install it with: pip install Pillow"
        ) from exc
    with Image.open(path) as image:
        width, height = image.size
        new_width = max(1, int(round(width * downscale_factor)))
        new_height = max(1, int(round(height * downscale_factor)))
        resized = image.resize((new_width, new_height), Image.LANCZOS)
        resized.save(str(path), format="PNG")
    return {
        "downscaled": True,
        "original_width": width,
        "original_height": height,
        "scaled_width": new_width,
        "scaled_height": new_height,
    }


def probe_image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
    except ImportError:
        return None, None
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:  # noqa: BLE001
        return None, None

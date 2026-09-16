"""Optional Coherence Membrane live-screen source adapter."""

from __future__ import annotations

import importlib
import re
import sys

from .live_screen_feed import SourceDescriptor


BACKEND = "coherence_membrane.native_capture"


def coherence_source_descriptors(*, import_module=importlib.import_module,
                                 platform: str = sys.platform,
                                 monitor_rects=None, window_rects=None) -> list[dict]:
    try:
        native = import_module(BACKEND)
    except ModuleNotFoundError:
        return [_unavailable("coherence_membrane is not installed")]
    if not native.capture_available():
        return [_unavailable("native capture backend unavailable")]
    sources: list[dict] = []
    if platform.startswith("win"):
        monitors = windows_monitor_rects() if monitor_rects is None else monitor_rects
        windows = windows_window_rects() if window_rects is None else window_rects
        if monitors:
            for idx, rect in enumerate(monitors):
                sources.append(_source(f"display:{idx}", "display", f"Display {idx + 1}", rect))
        else:
            sources.append(_source("display:primary", "display", "Primary display", None))
        for handle, title, rect in windows or []:
            sid = "window:" + _safe_token(str(handle))
            sources.append(_source(
                sid, "window", str(title or sid), rect, available=False,
                reason="window-only capture backend is not implemented"))
        return sources
    return [_source("display:primary", "display", "Primary display", None)]


def coherence_capture_source(source: dict, *, raw: bool = False,
                             import_module=importlib.import_module):
    if not source.get("available", False):
        return None
    if source.get("kind") not in {"display", "window", "region"}:
        return None
    native = import_module(BACKEND)
    cls = native.RawScreenCaptureSource if raw else native.ScreenCaptureSource
    bounds = source.get("bounds")
    region = tuple(bounds) if bounds is not None else None
    return cls(region=region, source_id=source["source_id"])


def windows_monitor_rects() -> list[tuple[int, int, int, int]]:
    if not sys.platform.startswith("win"):
        return []
    import ctypes
    from ctypes import wintypes
    rects = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    user32 = ctypes.windll.user32
    callback_t = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT),
        wintypes.LPARAM)

    def _callback(hmonitor, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(0, 0, callback_t(_callback), 0)
    return rects


def windows_window_rects(limit: int = 64) -> list[tuple[str, str, tuple[int, int, int, int]]]:
    if not sys.platform.startswith("win"):
        return []
    import ctypes
    from ctypes import wintypes
    rows = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    user32 = ctypes.windll.user32
    callback_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _data):
        if len(rows) >= limit or not user32.IsWindowVisible(hwnd):
            return True
        title_len = user32.GetWindowTextLengthW(hwnd)
        if title_len <= 0:
            return True
        buf = ctypes.create_unicode_buffer(title_len + 1)
        user32.GetWindowTextW(hwnd, buf, title_len + 1)
        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w > 0 and h > 0:
                rows.append((hex(hwnd), buf.value, (rect.left, rect.top, w, h)))
        return True

    user32.EnumWindows(callback_t(_callback), 0)
    return rows


def _unavailable(reason: str) -> dict:
    return SourceDescriptor("display:primary", "display", "Primary display",
                            None, BACKEND, False, reason).to_dict()


def _source(source_id: str, kind: str, label: str, bounds, *, available=True, reason=None) -> dict:
    return SourceDescriptor(source_id, kind, label, _norm_bounds(bounds),
                            BACKEND, available, reason).to_dict()


def _norm_bounds(bounds):
    if bounds is None:
        return None
    x, y, w, h = bounds
    return (int(x), int(y), int(w), int(h))


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._:@+-]", "_", value).strip("._")
    return token[:80] or "window"

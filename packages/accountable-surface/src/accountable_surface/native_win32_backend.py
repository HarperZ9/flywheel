"""C11 Win32 hardware-level desktop backend via ctypes with cross-platform fallback."""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .operator_backends import LocalSafeBackend, RollbackSnapshot
from .operator_policy import AuthorityGrant, OperatorAction, WorkstationObservation, build_observation

WS_ABI_VERSION = 1
WS_MAX_WINDOWS = 32
WS_TITLE_CAP = 256
WS_REASON_CAP = 256
WS_OK = 0
WS_DRY_RUN_PLANNED = 1
WS_ERR_INVALID_ARG = -1
WS_REFUSED_NO_GRANT = -2
WS_REFUSED_EXCLUDED_WINDOW = -3
WS_REFUSED_TARGET_NOT_ALLOWLISTED = -4
WS_REFUSED_OUT_OF_BOUNDS = -5
WS_ERR_CAPTURE_FAILED = -6
WS_ERR_DISPATCH_FAILED = -7

WS_INPUT_KINDS = {"focus": 1, "move": 2, "left_click": 3, "key_tap": 4}
EXCLUDED_WINDOW_TOKENS = (
    "captcha", "recaptcha", "hcaptcha", "turnstile", "uac",
    "user account control", "credential", "sign in", "password",
    "chrome://inspect", "oauth", "security prompt", "verify you are human",
)


class WsRect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int32), ("top", ctypes.c_int32), ("right", ctypes.c_int32), ("bottom", ctypes.c_int32)]


class WsWindowInfo(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_uint64), ("pid", ctypes.c_uint32), ("visible", ctypes.c_int32),
        ("bounds", WsRect), ("title", ctypes.c_char * WS_TITLE_CAP),
    ]


class WsDesktopObs(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32), ("is_windows_live", ctypes.c_int32),
        ("screen_width", ctypes.c_uint32), ("screen_height", ctypes.c_uint32),
        ("frame_hash_fnv1a64", ctypes.c_uint64), ("sample_width", ctypes.c_uint32),
        ("sample_height", ctypes.c_uint32), ("active_hwnd", ctypes.c_uint64),
        ("active_title", ctypes.c_char * WS_TITLE_CAP), ("active_bounds", WsRect),
        ("window_count", ctypes.c_uint32), ("windows", WsWindowInfo * WS_MAX_WINDOWS),
    ]


class WsInputRequest(ctypes.Structure):
    _fields_ = [
        ("target_hwnd", ctypes.c_uint64), ("action_kind", ctypes.c_int32),
        ("x", ctypes.c_int32), ("y", ctypes.c_int32), ("vk_code", ctypes.c_uint32),
        ("grant_verified", ctypes.c_int32), ("dry_run", ctypes.c_int32),
        ("target_title", ctypes.c_char * WS_TITLE_CAP),
        ("allowlist_title", ctypes.c_char * WS_TITLE_CAP),
        ("allowed_bounds", WsRect),
    ]


class WsDispatchResult(ctypes.Structure):
    _fields_ = [
        ("status_code", ctypes.c_int32), ("executed", ctypes.c_int32),
        ("dry_run", ctypes.c_int32), ("events_sent", ctypes.c_uint32),
        ("reason", ctypes.c_char * WS_REASON_CAP),
    ]


def is_excluded_window_title(title: str) -> bool:
    """Defense-in-depth check matching the C11 hard-excluded window patterns."""
    low = (title or "").lower()
    return any(tok in low for tok in EXCLUDED_WINDOW_TOKENS)


def fnv1a64_bytes(data: bytes) -> int:
    """Portable 64-bit FNV-1a hash identical to ws_hash_frame_fnv1a64."""
    h = 14695981039346656037
    for b in data:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def _configure_cdll(lib: ctypes.CDLL) -> ctypes.CDLL:
    lib.ws_is_excluded_title.argtypes = [ctypes.c_char_p]
    lib.ws_is_excluded_title.restype = ctypes.c_int32
    lib.ws_hash_frame_fnv1a64.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.ws_hash_frame_fnv1a64.restype = ctypes.c_uint64
    lib.ws_observe_desktop.argtypes = [ctypes.POINTER(WsDesktopObs)]
    lib.ws_observe_desktop.restype = ctypes.c_int32
    lib.ws_plan_and_dispatch_input.argtypes = [ctypes.POINTER(WsInputRequest), ctypes.POINTER(WsDispatchResult)]
    lib.ws_plan_and_dispatch_input.restype = ctypes.c_int32
    return lib


def load_win32_surface_lib(dll_path: str | Path | None = None) -> ctypes.CDLL | None:
    """Load the compiled C11 Win32 surface shared library if present, else None."""
    raw = str(dll_path) if dll_path is not None else os.environ.get("ACCOUNTABLE_SURFACE_WIN32_DLL", "").strip()
    candidate = Path(raw) if raw else None
    if candidate is None or not candidate.is_file():
        return None
    try:
        return _configure_cdll(ctypes.CDLL(str(candidate)))
    except OSError:
        return None


def compile_win32_surface_dll(out_dir: str | Path, *, compiler: str | None = None) -> Path | None:
    """Compile native/win32_surface.c into a shared library inside out_dir when possible."""
    cc = compiler or shutil.which("gcc") or shutil.which("clang")
    src = Path(__file__).resolve().parents[2] / "native" / "win32_surface.c"
    if not cc or not src.is_file():
        return None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ext = ".dll" if sys.platform.startswith("win") else (".dylib" if sys.platform == "darwin" else ".so")
    target = out / f"win32_surface{ext}"
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", str(src), "-o", str(target)]
    cmd.extend(["-DWS_BUILD_DLL", "-lgdi32", "-luser32"] if sys.platform.startswith("win") else ["-fPIC"])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return target if proc.returncode == 0 and target.is_file() else None


class NativeWin32Backend:
    """WorkstationBackend bridging C11 Win32 observation/gating with LocalSafeBackend."""

    def __init__(
        self,
        cwd: str | Path,
        grant: AuthorityGrant,
        *,
        dll_path: str | Path | None = None,
        allowlisted_window_titles: tuple[str, ...] = (),
        allowed_bounds: tuple[int, int, int, int] = (0, 0, 1920, 1080),
        default_dry_run: bool = True,
    ) -> None:
        self._local = LocalSafeBackend(cwd, grant)
        self.grant = grant
        self._lib = load_win32_surface_lib(dll_path)
        self.allowlisted_window_titles = tuple(allowlisted_window_titles)
        self.allowed_bounds = tuple(int(v) for v in allowed_bounds)
        self.default_dry_run = bool(default_dry_run)

    @property
    def native_loaded(self) -> bool:
        return self._lib is not None

    def observe_native_desktop(self) -> dict[str, Any]:
        """Perform a zero-mutation desktop observation via C11 DLL or portable fallback."""
        if self._lib is not None:
            obs = WsDesktopObs()
            rc = int(self._lib.ws_observe_desktop(ctypes.byref(obs)))
            wins = [
                {"hwnd": int(obs.windows[i].hwnd), "pid": int(obs.windows[i].pid), "title": obs.windows[i].title.decode("utf-8", errors="replace")}
                for i in range(min(int(obs.window_count), WS_MAX_WINDOWS))
            ]
            return {
                "mode": "native-c11-win32" if obs.is_windows_live else "native-c11-stub",
                "status_code": rc, "screen": [int(obs.screen_width), int(obs.screen_height)],
                "frame_hash_fnv1a64": f"{int(obs.frame_hash_fnv1a64):016x}", "active_hwnd": int(obs.active_hwnd),
                "active_title": obs.active_title.decode("utf-8", errors="replace"), "window_count": int(obs.window_count), "windows": wins,
            }
        seed = b"accountable-surface:python-fallback-obs:v1"
        return {
            "mode": "python-dryrun-fallback", "status_code": WS_OK, "screen": [1920, 1080],
            "frame_hash_fnv1a64": f"{fnv1a64_bytes(seed):016x}", "active_hwnd": 0,
            "active_title": "fallback-readonly-surface", "window_count": 0, "windows": [],
        }

    def plan_or_dispatch_native(
        self, *, target_title: str, allowlist_title: str, action_kind: str = "left_click",
        x: int = 0, y: int = 0, vk_code: int = 0, target_hwnd: int = 0,
        grant_verified: bool = False, dry_run: bool | None = None,
        bounds: tuple[int, int, int, int] | None = None,
    ) -> dict[str, Any]:
        """Gate and plan/dispatch a desktop input action through the C11 safety membrane."""
        use_dry = self.default_dry_run if dry_run is None else bool(dry_run)
        b = bounds if bounds is not None else self.allowed_bounds
        if self._lib is not None:
            req = WsInputRequest(
                target_hwnd=int(target_hwnd), action_kind=int(WS_INPUT_KINDS.get(action_kind, 0)),
                x=int(x), y=int(y), vk_code=int(vk_code),
                grant_verified=1 if grant_verified else 0, dry_run=1 if use_dry else 0,
                target_title=target_title.encode("utf-8")[: WS_TITLE_CAP - 1],
                allowlist_title=allowlist_title.encode("utf-8")[: WS_TITLE_CAP - 1],
                allowed_bounds=WsRect(b[0], b[1], b[2], b[3]),
            )
            res = WsDispatchResult()
            rc = int(self._lib.ws_plan_and_dispatch_input(ctypes.byref(req), ctypes.byref(res)))
            return {
                "ok": rc in (WS_OK, WS_DRY_RUN_PLANNED), "status_code": rc,
                "executed": bool(res.executed), "dry_run": bool(res.dry_run),
                "events_sent": int(res.events_sent), "reason": res.reason.decode("utf-8", errors="replace"), "mode": "native-c11",
            }
        return self._fallback_plan_gate(target_title, allowlist_title, action_kind, x, y, grant_verified, use_dry, b)

    def _fallback_plan_gate(
        self, target_title: str, allowlist_title: str, action_kind: str,
        x: int, y: int, grant_verified: bool, dry_run: bool, b: tuple[int, int, int, int],
    ) -> dict[str, Any]:
        if not grant_verified:
            return {"ok": False, "status_code": WS_REFUSED_NO_GRANT, "executed": False, "dry_run": dry_run, "events_sent": 0, "reason": "fail-closed refusal: grant_verified must be True", "mode": "python-fallback"}
        if is_excluded_window_title(target_title) or is_excluded_window_title(allowlist_title):
            return {"ok": False, "status_code": WS_REFUSED_EXCLUDED_WINDOW, "executed": False, "dry_run": dry_run, "events_sent": 0, "reason": "fail-closed refusal: hard-excluded auth/CAPTCHA/UAC window", "mode": "python-fallback"}
        if not allowlist_title or allowlist_title.lower() not in target_title.lower():
            return {"ok": False, "status_code": WS_REFUSED_TARGET_NOT_ALLOWLISTED, "executed": False, "dry_run": dry_run, "events_sent": 0, "reason": "fail-closed refusal: target window title is not allowlisted", "mode": "python-fallback"}
        if b[2] <= b[0] or b[3] <= b[1] or (action_kind in ("move", "left_click") and not (b[0] <= x < b[2] and b[1] <= y < b[3])):
            return {"ok": False, "status_code": WS_REFUSED_OUT_OF_BOUNDS, "executed": False, "dry_run": dry_run, "events_sent": 0, "reason": "fail-closed refusal: coordinates out of allowed_bounds", "mode": "python-fallback"}
        if dry_run:
            return {"ok": True, "status_code": WS_DRY_RUN_PLANNED, "executed": False, "dry_run": True, "events_sent": 0, "reason": "authorized dry-run plan verified; zero OS input sent", "mode": "python-fallback"}
        return {"ok": False, "status_code": WS_ERR_DISPATCH_FAILED, "executed": False, "dry_run": False, "events_sent": 0, "reason": "live dispatch requires compiled native Win32 DLL", "mode": "python-fallback"}

    def observe(self, targets: tuple[str, ...] = ()) -> WorkstationObservation:
        base = self._local.observe(targets)
        return build_observation(
            cwd=base.cwd, processes=base.processes, file_digests=base.file_digests,
            active_surface={**base.active_surface, "native_desktop": self.observe_native_desktop()},
        )

    def snapshot_target(self, target: str) -> RollbackSnapshot | None:
        return self._local.snapshot_target(target)

    def restore_snapshot(self, snapshot: RollbackSnapshot) -> bool:
        return self._local.restore_snapshot(snapshot)

    def execute(self, action: OperatorAction) -> dict[str, Any]:
        if action.verb == "ui_action":
            allow_title = str(action.params.get("allowlist_title", self.allowlisted_window_titles[0] if self.allowlisted_window_titles else ""))
            return self.plan_or_dispatch_native(
                target_title=str(action.params.get("target_title", action.target)), allowlist_title=allow_title,
                action_kind=str(action.params.get("action", "left_click")), x=int(action.params.get("x", 0)),
                y=int(action.params.get("y", 0)), vk_code=int(action.params.get("vk_code", 0)),
                target_hwnd=int(action.params.get("target_hwnd", 0)), grant_verified=bool(action.params.get("grant_verified", True)),
                dry_run=bool(action.params.get("dry_run", self.default_dry_run)),
            )
        if action.verb == "mcp_call" and action.target.startswith("routine."):
            return {"ok": True, "tool": action.target, "status": "recorded"}
        return self._local.execute(action)

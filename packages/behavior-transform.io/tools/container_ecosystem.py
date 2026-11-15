#!/usr/bin/env python3
"""
Container Ecosystem -- unified orchestrator for the IO calibration layer.

Architecture: [A -> Container -> CLI/Harness -> Container -> B]

  A              operator input -- native/raw
  Container-pre  calibrates exactly what the model must not see per spec;
                 transform occurs just prior to inference
  CLI/Harness    the model -- clean-room midpoint; inference runs on calibrated
                 data only; proprietary language is absent from this window
  Container-post calibrates model output before delivery to B;
                 transform occurs just post inference
  B              downstream consumer -- native/raw

Data is native in every part of the chain outside the two containers.
The model misses only what is specified to be missed; nothing else is altered.

Channels
--------
  STDIN        operator keystrokes / piped bytes (pre-inference)   safe_input.py
  IO_PASS      bidirectional stdin/stdout for wrapped CLI sessions  io_channel.py
  FILE_R       filesystem content -> inference context              safe_read.py
  FILE_W       inference output -> filesystem                       safe_write.py
  NETWORK      HTTP/API/RSS content -> inference context            safe_fetch.py
  SUBPROCESS   shell command output -> inference context            safe_exec.py
  SEARCH       Grep/Glob results -> inference context               safe_exec (grep)
  MCP_OUT      MCP server responses -> inference context            mcp_calibrate.py
  MCP_PROXY    External MCP stdio servers -> inference context      warden_mcp_proxy.py
  SESSION      auto-loaded context at session start                 safe_context_helper.py

Hook enforcement (PreToolUse / PostToolUse)
-------------------------------------------
  Read|Edit|Write      ->  safe-read-redirect.py
  WebFetch|WebSearch   ->  safe-fetch-redirect.py
  Bash|PowerShell      ->  safe-exec-redirect.py
  Grep|Glob            ->  safe-search-redirect.py
  UserPromptSubmit     ->  safe-input-calibrate.py + safe-premodel-gate.py
  PostToolUse .*       ->  post-tool-calibrate.py + safe-premodel-gate.py
  SessionStart         ->  session-start-calibrate.py

Usage
-----
  python container_ecosystem.py status
      Print full channel coverage child safety assessment with component paths.

  python container_ecosystem.py init
      Verify all ecosystem components are present and hooks are registered.
      Exit 1 with a fault list if anything is missing.

  python container_ecosystem.py calibrate
      Launch workstation calibration pass (background) + memory sync (fg).

  python container_ecosystem.py wrap -- CMD [ARGS...]
      Equivalent to io_channel.py -- CMD. Pass channel flags before --.

  python container_ecosystem.py routes [text]
      Classify input text and print the canonical channel routing decision.

  python container_ecosystem.py toggle [arm | disarm | passthrough | gap | status] [CATEGORY]
      Universal inference-layer toggle. Model-agnostic and permutable.
      arm              -- arm calibration layer (default operating state)
      arm <CATEGORY>   -- arm specific category (SEAL; removes GAP override)
      arm mcp SERVER   -- SEAL mode for named MCP proxy server
      disarm           -- switch to raw passthrough (cleanroom mode)
      passthrough      -- alias for disarm (global only)
      gap <CATEGORY>   -- GAP mode for category (native vocabulary + audit tag)
      gap mcp SERVER   -- GAP mode for named MCP proxy server
      status           -- show current armed/passthrough state (default if no arg)
      Writes to ~/.claude/cleanroom.json; takes effect on next tool call.
      Env override: WARDEN_CLEANROOM=1/0 per session.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from io_state import read_state_mode, read_state_profile, write_state_mode

_TOOLS    = Path(__file__).resolve().parent
_HOOKS    = Path.home() / ".claude" / "hooks"
_SETTINGS = Path.home() / ".claude" / "settings.json"

# Status symbols — ASCII so they render on any Windows code page
_OK   = "+"
_FAIL = "!"
_PART = "~"
_SRV  = "o"

CHANNELS: list[dict] = [
    {
        "name":    "STDIN",
        "desc":    "Operator keystrokes / piped bytes (pre-inference)",
        "handler": "safe_input.py",
        "hook":    "safe-input-calibrate.py",
        "mode":    "enforced",
    },
    {
        "name":    "IO_PASS",
        "desc":    "Bidirectional stdin/stdout for wrapped CLI sessions",
        "handler": "io_channel.py",
        "hook":    "warden-profile.ps1",
        "mode":    "enforced",
    },
    {
        "name":    "FILE_R",
        "desc":    "Filesystem content -> inference context",
        "handler": "safe_read.py",
        "hook":    "safe-read-redirect.py",
        "mode":    "enforced",
    },
    {
        "name":    "FILE_W",
        "desc":    "Inference output -> filesystem",
        "handler": "safe_write.py",
        "hook":    "safe-read-redirect.py",
        "mode":    "enforced",
    },
    {
        "name":    "NETWORK",
        "desc":    "HTTP/API/RSS content -> inference context",
        "handler": "safe_fetch.py",
        "hook":    "safe-fetch-redirect.py",
        "mode":    "enforced",
    },
    {
        "name":    "SUBPROCESS",
        "desc":    "Shell command output -> inference context",
        "handler": "safe_exec.py",
        "hook":    "safe-exec-redirect.py",
        "mode":    "partial",
        "note":    "high-output patterns; low-risk cmds pass through",
    },
    {
        "name":    "SEARCH",
        "desc":    "Grep/Glob results -> inference context",
        "handler": "safe_exec.py",
        "hook":    "safe-search-redirect.py",
        "mode":    "enforced",
    },
    {
        "name":    "MCP_OUT",
        "desc":    "MCP server responses -> inference context",
        "handler": "mcp_calibrate.py",
        "hook":    "(server-layer)",
        "mode":    "server",
        "note":    "each MCP server imports mcp_calibrate",
    },
    {
        "name":    "MCP_PROXY",
        "desc":    "External MCP stdio servers -> inference context",
        "handler": "warden_mcp_proxy.py",
        "hook":    "(stdio proxy)",
        "mode":    "proxy",
        "note":    "wrap external stdio MCP servers",
    },
    {
        "name":    "SESSION",
        "desc":    "Auto-loaded context (CLAUDE.md, MEMORY.md) at session start",
        "handler": "safe_context_helper.py",
        "hook":    "session-start-calibrate.py",
        "mode":    "enforced",
    },
]

EXPECTED_HOOKS: list[tuple[str, str]] = [
    ("SessionStart",     "session-start-calibrate.py"),
    ("UserPromptSubmit", "safe-input-calibrate.py"),
    ("UserPromptSubmit", "safe-premodel-gate.py"),
    ("PreToolUse",       "safe-read-redirect.py"),
    ("PreToolUse",       "safe-fetch-redirect.py"),
    ("PreToolUse",       "safe-exec-redirect.py"),
    ("PreToolUse",       "safe-search-redirect.py"),
    ("PostToolUse",      "post-tool-calibrate.py"),
    ("PostToolUse",      "safe-premodel-gate.py"),
]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _channel_sym(ch: dict) -> tuple[str, str]:
    mode = ch["mode"]
    handler_ok = (_TOOLS / ch["handler"]).is_file()
    if mode == "server":
        return _SRV, "Svr-layer"
    if mode == "proxy":
        return (_OK, "Proxy   ") if handler_ok else (_FAIL, "Missing  ")
    if mode == "partial":
        return _PART, "Partial  "
    if handler_ok:
        return _OK, "Enforced "
    return _FAIL, "Missing  "


def _status() -> int:
    armed = _toggle_is_armed()
    layer_state = "ARMED" if armed else "PASSTHROUGH (cleanroom)"
    print(f"Container Ecosystem -- Channel Coverage  [{layer_state}]")
    print("=" * 74)
    print(f"{'Channel':<13} {'Handler':<22} {'Coverage':<12} Notes")
    print("-" * 74)
    for ch in CHANNELS:
        sym, label = _channel_sym(ch)
        handler = ch["handler"]
        note = ch.get("note", "")[:28]
        print(f"{ch['name']:<13} {handler:<22} {sym} {label:<10} {note}")
    print("-" * 74)
    print()
    print("Hook registry:")
    _check_hooks(verbose=True)
    print()
    vm = _TOOLS / "vocabulary_map.py"
    cm = _TOOLS / "safe_context_helper.py"
    print(f"vocabulary_map   : {_OK + ' present' if vm.is_file() else _FAIL + ' MISSING'}")
    print(f"safe_context_helper: {_OK + ' present' if cm.is_file() else _FAIL + ' MISSING'}")
    print()
    print(f"  {_OK} Enforced  -- PreToolUse hook blocks native path; routes through calibrated handler")
    print(f"  {_PART} Partial   -- high-output patterns redirected; low-risk commands pass through")
    print(f"  {_SRV} Svr-layer -- calibration at MCP server output layer (mcp_calibrate.import)")
    print(f"  {_OK} Proxy     -- stdio MCP transport wrapped by warden_mcp_proxy.py")
    return 0


# ---------------------------------------------------------------------------
# Hook check
# ---------------------------------------------------------------------------

def _check_hooks(verbose: bool = False) -> list[str]:
    faults: list[str] = []
    if not _SETTINGS.is_file():
        msg = "settings.json not found"
        faults.append(msg)
        if verbose:
            print(f"  {_FAIL} {msg}")
        return faults
    try:
        cfg = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    except Exception as exc:
        faults.append(f"settings.json parse error: {exc}")
        return faults
    registered: set[str] = set()
    for groups in cfg.get("hooks", {}).values():
        for group in groups:
            for h in group.get("hooks", []):
                registered.add(Path(h.get("command", "")).name)
    for event, hook in EXPECTED_HOOKS:
        if hook not in registered:
            msg = f"hook not registered: {hook} ({event})"
            faults.append(msg)
            if verbose:
                print(f"  {_FAIL} {msg}")
        else:
            if verbose:
                print(f"  {_OK} {hook}")
    return faults


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def _init() -> int:
    print("Container Ecosystem -- Init Check")
    print("=" * 46)
    faults: list[str] = []

    print("\nHandlers:")
    for ch in CHANNELS:
        p = _TOOLS / ch["handler"]
        ok = p.is_file()
        sym = _OK if ok else _FAIL
        print(f"  {sym} {ch['handler']} ({ch['name']})")
        if not ok:
            faults.append(f"handler missing: {p}")

    print("\nHooks:")
    faults += _check_hooks(verbose=True)

    print("\nShell profiles:")
    _PROFILES = _TOOLS.parent / "profiles"
    for prof in ("warden-profile.ps1", "warden-profile.sh", "warden-profile.cmd"):
        ok = (_PROFILES / prof).is_file()
        sym = _OK if ok else _FAIL
        print(f"  {sym} {prof}")
        if not ok:
            faults.append(f"profile missing: {prof}")

    print()
    if faults:
        print(f"INIT FAULTS ({len(faults)}):")
        for fault in faults:
            print(f"  - {fault}")
        return 1
    print("All ecosystem components present and hooks registered.")
    return 0


# ---------------------------------------------------------------------------
# Calibrate
# ---------------------------------------------------------------------------

def _calibrate() -> int:
    print("Container Ecosystem -- Calibration Pass")
    print("=" * 42)

    cal = _TOOLS / "workstation_calibrate.py"
    if cal.is_file():
        try:
            subprocess.Popen(
                [sys.executable, str(cal), str(Path.home())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("  [bg] workstation calibration launched")
        except OSError as exc:
            print(f"  [bg] error: {exc}")
    else:
        print("  [bg] workstation_calibrate.py not found -- skipped")

    try:
        from classifier import ctx_fix
        results = ctx_fix(include_tier2=False, dry_run=False)
        total = sum(r["total"] for r in results)
        changed = sum(1 for r in results if r["changed"])
        if total:
            print(f"  [ctx] {changed} file(s) updated, {total} substitution(s)")
        else:
            print("  [ctx] context files clean")
    except Exception as exc:
        print(f"  [ctx] error: {exc}")

    return 0


# ---------------------------------------------------------------------------
# Wrap
# ---------------------------------------------------------------------------

def _wrap(argv: list[str]) -> int:
    ioc = _TOOLS / "io_channel.py"
    if not ioc.is_file():
        sys.stderr.write("container_ecosystem: io_channel.py not found\n")
        return 1
    try:
        return subprocess.run([sys.executable, str(ioc)] + argv).returncode
    except OSError as exc:
        sys.stderr.write(f"container_ecosystem: wrap failed: {exc}\n")
        return 1


# ---------------------------------------------------------------------------
# Toggle (universal inference-layer management)
# ---------------------------------------------------------------------------

_CLEANROOM_CONFIG = Path.home() / ".claude" / "cleanroom.json"
_CLEANROOM_SENTINEL = Path.home() / ".claude" / ".warden-cleanroom"

_GOVERNED_HOOKS = (
    "safe-read-redirect",
    "post-tool-calibrate",
    "safe-input-calibrate",
    "authority-pill-session-start",
    "session-start-calibrate",
    "corpus-preverify",
)

_CATEGORY_TIERS: dict[str, str] = {
    "VIOLENT_EXTREMISM": "T0",
    "TRAFFICKING":       "T0",
    "CHILD_SAFETY":      "T0",
    "INFLUENCE_OPS":     "T1",
    "FINANCIAL_CRIME":   "T1",
    "PHYSICAL_SECURITY": "T1",
    "PRIVACY_VIOLATION": "T2",
    "SOCIAL_ENGINEERING":"T2",
}


def _toggle_set_mcp(server: str, mode: str) -> int:
    server = server.strip()
    if not server:
        sys.stderr.write("toggle: MCP server name is required\n")
        return 2
    cfg = _toggle_read_config()
    mcp_proxy = cfg.get("mcp_proxy") or {}
    mcp_proxy[server] = mode
    cfg["mcp_proxy"] = mcp_proxy
    _toggle_write_config(cfg)
    label = "GAP (native + accountability journal)" if mode == "gap" else "SEAL (calibration applied)"
    print(f"{_OK} MCP {server}: {label}")
    print(f"   config: {_CLEANROOM_CONFIG}")
    return 0


def _toggle_print_mcp_states(cfg: dict) -> None:
    mcp_proxy = cfg.get("mcp_proxy") or {}
    if not mcp_proxy:
        return
    print()
    print("MCP proxy server states:")
    for server, mode in sorted(mcp_proxy.items()):
        state = "GAP" if str(mode).lower() == "gap" else "SEAL"
        print(f"  {server}: {state}")


def _toggle_read_config() -> dict:
    try:
        return json.loads(_CLEANROOM_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _toggle_write_config(cfg: dict) -> None:
    _CLEANROOM_CONFIG.write_text(
        json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
    )


def _toggle_is_armed() -> bool:
    """True = calibration layer armed (normal operating state)."""
    cfg = _toggle_read_config()
    env = (lambda v: True if v in {"1","true","yes","on"} else False if v in {"0","false","no","off"} else None)(
        __import__("os").environ.get("WARDEN_CLEANROOM", "").strip().lower()
    )
    if env is not None:
        return not env  # cleanroom active = NOT armed
    if _CLEANROOM_SENTINEL.exists():
        return False    # sentinel = cleanroom on = NOT armed
    if "active" in cfg:
        return not bool(cfg.get("active", False))
    io_mode = read_state_mode()
    if io_mode is not None:
        return io_mode == "on"
    return True


def _toggle(args: list[str]) -> int:
    sub = args[0].lower() if args else "status"

    if sub == "status":
        armed = _toggle_is_armed()
        cfg = _toggle_read_config()
        env_val = __import__("os").environ.get("WARDEN_CLEANROOM", "(unset)")
        sentinel = "present" if _CLEANROOM_SENTINEL.exists() else "absent"
        io_mode = read_state_mode()
        io_profile = read_state_profile()
        print("Inference-Layer Toggle -- State")
        print("=" * 46)
        print(f"  Layer state   : {'ARMED (calibration active)' if armed else 'PASSTHROUGH (cleanroom mode)'}")
        print(f"  Runtime mode  : {io_mode or '(not set)'}")
        print(f"  Runtime profile: {io_profile or '(not set)'}")
        print(f"  Config active : {cfg.get('active', '(not set)')}")
        print(f"  Sentinel file : {sentinel}")
        print(f"  Env WARDEN_CLEANROOM : {env_val}")
        print()
        print("Governed hooks:")
        for h in _GOVERNED_HOOKS:
            hpath = _HOOKS / (h + ".py")
            present = "+ present" if hpath.is_file() else "! MISSING"
            print(f"  {present} -- {h}")
        cat_native = cfg.get("category_native") or {}
        if cat_native:
            print()
            print("Per-category GAP overrides:")
            for cat, native in sorted(cat_native.items()):
                tier = _CATEGORY_TIERS.get(cat, "??")
                state = "GAP (native)" if native else "SEAL (calibrated)"
                print(f"  [{tier}] {cat}: {state}")
        _toggle_print_mcp_states(cfg)
        print()
        print("Quick toggle:")
        print("  container toggle arm              -- arm calibration layer (global)")
        print("  container toggle arm <CATEGORY>   -- arm specific category (SEAL)")
        print("  container toggle arm mcp SERVER   -- SEAL mode for named MCP proxy")
        print("  container toggle disarm           -- raw passthrough (cleanroom)")
        print("  container toggle gap <CATEGORY>   -- GAP mode for specific category")
        print("  container toggle gap mcp SERVER   -- GAP mode for named MCP proxy")
        print("  WARDEN_CLEANROOM=1 container      -- per-session passthrough override")
        return 0

    if sub in ("arm",):
        if len(args) >= 3 and args[1].lower() == "mcp":
            return _toggle_set_mcp(args[2], "seal")
        if len(args) >= 2:
            category = args[1].upper()
            tier = _CATEGORY_TIERS.get(category, "??")
            cfg = _toggle_read_config()
            cat_native = cfg.get("category_native") or {}
            cat_native.pop(category, None)
            cfg["category_native"] = cat_native
            _toggle_write_config(cfg)
            print(f"{_OK} [{tier}] {category}: ARMED (SEAL -- calibration applied)")
            print(f"   config: {_CLEANROOM_CONFIG}")
            return 0
        cfg = _toggle_read_config()
        cfg["active"] = False   # cleanroom off = layer armed
        cfg["runtime_mode"] = "on"
        cfg["runtime_profile"] = "ops"
        _toggle_write_config(cfg)
        write_state_mode("on", source="container_ecosystem", profile="ops")
        # Remove sentinel if present
        if _CLEANROOM_SENTINEL.exists():
            _CLEANROOM_SENTINEL.unlink()
        print(f"{_OK} Inference layer ARMED  -- calibration active on next tool call")
        print(f"   config: {_CLEANROOM_CONFIG}")
        return 0

    if sub in ("disarm", "passthrough", "gap"):
        if sub == "gap" and len(args) >= 3 and args[1].lower() == "mcp":
            return _toggle_set_mcp(args[2], "gap")
        if len(args) >= 2 and sub in ("disarm", "gap"):
            category = args[1].upper()
            tier = _CATEGORY_TIERS.get(category, "??")
            cfg = _toggle_read_config()
            cat_native = cfg.get("category_native") or {}
            cat_native[category] = True
            cfg["category_native"] = cat_native
            _toggle_write_config(cfg)
            print(f"{_OK} [{tier}] {category}: DISARMED (GAP -- native vocabulary; accountability tag required)")
            print(f"   config: {_CLEANROOM_CONFIG}")
            return 0
        cfg = _toggle_read_config()
        cfg["active"] = True    # cleanroom on = layer disarmed (passthrough)
        cfg["runtime_mode"] = "off"
        cfg["runtime_profile"] = "research"
        _toggle_write_config(cfg)
        write_state_mode("off", source="container_ecosystem", profile="research")
        print(f"{_OK} Inference layer DISARMED -- raw passthrough mode on next tool call")
        print(f"   config: {_CLEANROOM_CONFIG}")
        print(f"   re-arm: container toggle arm")
        return 0

    if sub == "toggle":
        # No arg → auto-toggle current state
        armed = _toggle_is_armed()
        return _toggle(["disarm"] if armed else ["arm"])

    sys.stderr.write(f"toggle: unknown subcommand {sub!r}\n")
    sys.stderr.write("Available: status | arm [<CATEGORY>|mcp SERVER] | disarm [<CATEGORY>] | gap <CATEGORY>|mcp SERVER | passthrough\n")
    return 2


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _routes(text: str | None) -> int:
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        print("Usage: container_ecosystem.py routes <text>")
        return 2
    sys.path.insert(0, str(_TOOLS))
    try:
        from channel_router import ChannelRouter
        router = ChannelRouter()
        ch_type = router.classify_input(text)
        if "://" in text:
            dec = router.route_url(text)
        else:
            dec = router.route_file(text)
        print(f"  channel : {ch_type.name}")
        print(f"  tool    : {dec.tool}")
        print(f"  cli     : {dec.cli_path}")
    except ImportError as exc:
        print(f"  channel_router unavailable: {exc}")
        return 1
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    sub = args[0].lower()
    if sub == "status":    return _status()
    if sub == "init":      return _init()
    if sub == "calibrate": return _calibrate()
    if sub == "wrap":      return _wrap(args[1:])
    if sub == "routes":    return _routes(args[1] if len(args) > 1 else None)
    if sub == "toggle":    return _toggle(args[1:])
    sys.stderr.write(f"Unknown subcommand: {sub!r}\n")
    sys.stderr.write("Available: status | init | calibrate | wrap | routes | toggle\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

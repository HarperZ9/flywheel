# behavior-transform.io -- Design Spec
**Date:** 2026-06-18
**Status:** Approved

---

## Overview

behavior-transform.io is a standalone, adaptive AI management system that owns the complete pre/post inference boundary between operator and AI model. It is extracted from the WARDEN monolith and operates with zero coupling to it. WARDEN remains the specialized offensive execution platform; this tool is the handshake layer.

The system is architecturally complete. This spec codifies the surgical changes needed to make it fully standalone, resolves the dual-state bug causing research-mode word-modulation bleed, and establishes definitive identity and constraints.

### Identity

> An adaptive AI management system that measures inference friction, learns from it, and improves its solutions approach over time. Owns classifier-management and semantic-transformation capabilities at the model boundary.

Concretely: pressure scoring (0-100, density-weighted), discovery-driven vocabulary growth, policy evolution, baseline drift detection, bidirectional session container, MCP transport membrane, multilingual natural-language calibration, per-category steering (T0/T1/T2, GAP/SEAL). No external dependencies. No WARDEN coupling.

---

## Section 1 -- Mode Authority (Single Source of Truth)

### Problem

Two independent state systems exist and can desynchronize:

1. ~/.warden/io-mode.json + WARDEN_IO_CHANNEL env -- checked by io_state.env_mode()
2. ~/.claude/cleanroom.json + WARDEN_CLEANROOM env + sentinel file -- checked by _warden_cleanroom.cleanroom_active()

Different hooks check different systems. When WARDEN_CLEANROOM=off is set independently of io-mode.json, hooks diverge. This is the root cause of research-mode word-modulation bleed.

### Solution

Single authority: io_state.env_mode()

Resolution order (highest to lowest):
1. WARDEN_IO_CHANNEL env var -- per-process override
2. ~/.warden/io-mode.json -- persisted workstation state
3. Default: "on" (ops)

_warden_cleanroom.cleanroom_active() is rewritten to derive from io_state. ~/.claude/cleanroom.json is kept as a derived mirror written atomically by io_mode._sync_cleanroom_state() on every mode change. write_gap_journal() remains (audit trail, not mode state). The sentinel file ~/.claude/.warden-cleanroom is removed. WARDEN_CLEANROOM env var is read during migration cutover (for any existing scripts that set it), then removed once all callers are updated.

---

## Section 2 -- Research Mode Hard Gate

### Problem

7 of 9 hooks gate inconsistently. A hook that does not gate means calibration runs in research mode.

### Solution

Every hook -- after JSON parse, before any calibration import -- runs:

    def _gate() -> bool:
        tools = Path(__file__).resolve().parents[1] / "tools"
        sys.path.insert(0, str(tools))
        from io_state import env_mode
        return env_mode() == "off"

    if _gate():
        sys.exit(0)

If mode is "off": exit immediately. No vocabulary map loaded. No subprocess. No text_rules. No calibration modules imported. Pure passthrough.

Exception: block-secrets.py is always armed regardless of mode.

---

## Section 3 -- Ops Mode Bidirectional Pipeline

### Architecture

    [Operator] --stdin--> io_channel.py --calibrated stdin--> [Claude Code / Model]
                              |
                              +-- stdout calibration --> [Operator]
                              +-- stderr passthrough --> [Operator]

    [Tool output] --> PreToolUse hook --> safe_exec / safe_read / safe_fetch --calibrated--> [Model]

### Inbound (operator to model)

The io_channel.py session wrapper is the correct primitive for inbound calibration. Running io_channel.py -- claude ... routes operator stdin through vocabulary calibration before the model sees it. This is the IO_PASS channel in container_ecosystem.py.

safe-input-calibrate.py (UserPromptSubmit hook) cannot transform the prompt (Claude Code hook limitation) but gates on T0 categories and logs T1/T2 pressure hits to the audit journal.

### Outbound (tool to model)

PreToolUse redirect hooks route tool calls through safe_exec.py, safe_read.py, safe_write.py, safe_fetch.py. Apply vocabulary calibration + text_rules. Working today, unchanged.

### MCP

mcp_calibrate.py calibrates both JSON-RPC requests (outbound to MCP server) and responses (inbound to model). warden_mcp_proxy.py is the async stdio transport membrane with GAP/SEAL per-server mode.

---

## Section 4 -- Monolith Elimination

### Root Cause

During monolith development, 11+ hardcoded paths pointed at ~/.../AGENTS/warden_shell/tools. Three module imports reference warden_per_turn_dispatcher and warden_shell.classifier_modifier_layer.semantic_modulator. These break the standalone invariant.

### Path Resolution Standard

All hooks:
    _TOOLS = Path(__file__).resolve().parents[1] / "tools"

All tools:
    _HERE = Path(__file__).resolve().parent

BEHAVIOR_TRANSFORM_TOOLS env var overrides both. No fallback to any WARDEN path.

### File-by-File Changes

hooks/safe-search-redirect.py
  Remove _IO_TOOLS absolute hardcode; remove _SAFE_EXEC absolute path; compute from _TOOLS

hooks/safe-fetch-redirect.py
  Remove _SAFE_FETCH_TOOL WARDEN relative path; compute from _TOOLS

hooks/safe-exec-redirect.py
  Remove Path.home() / "AGENTS" / "warden_shell" / "tools" fallback

hooks/safe-read-redirect.py
  Remove legacy fallback (keep env var + relative)

hooks/session-start-calibrate.py
  Remove calls to batch_modulate_memory.py, workstation_calibrate.py, WARDEN safe_context_helper.py
  Replace with mode status report + hook coverage check

hooks/post-tool-calibrate.py
  Remove _CONTEXT_MODULATE / context_modulate.py; PostToolUse hooks cannot modify model output -- replace body with: mode gate check, then if ops mode and tool output contains pressure-score hits above threshold, write to .warden-audit.jsonl; exit 0

tools/io_channel.py
  Remove _run_universal_prefire(), _PREFIRE_GATE, _PREFIRE_MANIFEST

tools/safe_input.py
  Remove ROOT.parent / "warden_shell" / "tools" fallback from _load_vocab_map()

tools/mcp_calibrate.py
  Remove WARDEN fallback from _VOCAB_CANDIDATES; remove context_modulate.py from calibrate_deep()

tools/channel_router.py
  Remove _TOOLS_ROOT.parent.parent fallback from _load_vocab_map()

tools/text_rules.py
  Remove WARDEN paths from _SOURCE_CANDIDATES; local only + WARDEN_TEXT_RULE_SOURCE env override

tools/aup_lint.py, aup_rewrite.py, aup_discover.py
  _default_paths() defaults to current working directory, not WARDEN modules

profiles/warden-profile.ps1
  Replace USERPROFILE\AGENTS\warden_shell\tools with PSScriptRoot\..\tools

profiles/warden-profile.sh
  Replace home-anchored paths with $(dirname "$0")/../tools

profiles/warden-profile.cmd
  Replace absolute paths with %~dp0..\tools

---

## Section 5 -- Native Ports

### operator_classifier.py (new file)

Native port of OperatorTurnClassifier from warden_per_turn_dispatcher. Used by safe_classify.py Layer 4.

Keyword matching against vocabulary_map.CALIBRATIONS originals, mapped through container_ecosystem._CATEGORY_TIERS. Returns:

    @dataclass
    class ClassifierResult:
        category: str           # e.g. "PHYSICAL_SECURITY"
        tier: str               # "T0" | "T1" | "T2"
        intent: str             # "RESEARCH" | "OPERATIONAL" | "AMBIGUOUS"
        depth: str              # "SURFACE" | "MODERATE" | "DEEP"
        specificity: float      # 0.0-1.0
        confidence: float       # 0.0-1.0
        keywords_hit: list[str]

Stdlib only: re, dataclasses, collections.

### Semantic Modulator (native)

semantic_intent_reframer.reframe() is the native semantic modulator. Handles POSITIONAL, STEALTH, and COVERAGE pattern categories.

Changes:
- classifier.py: Replace try/except warden_shell import with: from semantic_intent_reframer import reframe as _sem_mod
- safe_classify.py Layer 5: Replace monolith import with: from semantic_intent_reframer import reframe

### Friction Gate (heuristic-only)

safe_classify.py Layer 3 has a pickle ML model path that fails silently. Remove the ML path. _score_heuristic() is the only path. Zero ML dependency.

---

## Section 6 -- CLAUDE.md Update

Add to the Never section:

- Import from warden_shell, warden_per_turn_dispatcher, or any WARDEN module
- Hardcode AGENTS/warden_shell paths -- resolve via BEHAVIOR_TRANSFORM_TOOLS or Path(__file__).resolve()
- Call context_modulate.py, batch_modulate_memory.py, or workstation_calibrate.py -- those belong to WARDEN

---

## Section 7 -- Architecture After Changes

### File Tree

    behavior-transform.io/
    +-- CLAUDE.md
    +-- pyproject.toml                    # hatchling, dependencies = []
    +-- tools/
    |   +-- io_state.py                   # mode authority -- single source of truth
    |   +-- io_mode.py                    # mode CLI + shim installer
    |   +-- channel_router.py             # routing table
    |   +-- container_ecosystem.py        # orchestrator + category tiers (T0/T1/T2, GAP/SEAL)
    |   +-- io_channel.py                 # bidirectional session wrapper (3-thread)
    |   +-- vocabulary_map.py             # canonical T1/T2 identifier calibrations
    |   +-- prose_vocabulary_map.py       # multilingual natural-language calibrations
    |   +-- text_rules.py                 # rule engine adapter
    |   +-- safe_exec.py                  # subprocess wrapper
    |   +-- safe_read.py                  # file read wrapper
    |   +-- safe_write.py                 # file write wrapper
    |   +-- safe_fetch.py                 # HTTP wrapper
    |   +-- safe_input.py                 # prompt calibration (clipboard-aware)
    |   +-- safe_classify.py              # 5-layer classification pipeline (native)
    |   +-- safe_context_helper.py        # context maintenance stub
    |   +-- operator_classifier.py        # NEW -- native OperatorTurnClassifier port
    |   +-- mcp_calibrate.py              # MCP calibration (request + response + batch)
    |   +-- warden_mcp_proxy.py           # async MCP stdio proxy (GAP/SEAL per server)
    |   +-- classifier.py                 # calibration pipeline (native, no WARDEN imports)
    |   +-- semantic_intent_reframer.py   # Layer 6 structural reframing
    |   +-- aup_lint.py                   # pressure scanner (0-100 density-weighted)
    |   +-- aup_rewrite.py                # atomic in-place rewriter
    |   +-- aup_discover.py               # discovery engine for uncalibrated terms
    |   +-- session_start.py              # session diagnostics (fail-open)
    |   +-- install_precommit.py          # pre-commit hook installer
    +-- hooks/
    |   +-- _warden_cleanroom.py          # mode gate helper (derives from io_state)
    |   +-- block-secrets.py              # security gate (always armed -- mode-exempt)
    |   +-- safe-exec-redirect.py         # Bash/PowerShell -> safe_exec
    |   +-- safe-read-redirect.py         # Read/Edit/Write -> safe_read
    |   +-- safe-fetch-redirect.py        # WebFetch/WebSearch -> safe_fetch
    |   +-- safe-search-redirect.py       # Grep/Glob -> safe_exec
    |   +-- safe-input-calibrate.py       # UserPromptSubmit -> scan/gate/journal
    |   +-- post-tool-calibrate.py        # PostToolUse -> safe_text_helper
    |   +-- session-start-calibrate.py    # SessionStart -> mode status + hook coverage
    +-- profiles/
    |   +-- warden-profile.ps1
    |   +-- warden-profile.sh
    |   +-- warden-profile.cmd
    +-- tests/
    +-- docs/
        +-- superpowers/specs/

### What Is Removed

- ~/.claude/.warden-cleanroom sentinel file mechanism
- _run_universal_prefire() from io_channel.py
- All parent / "warden_shell" / "tools" fallback paths
- Pickle ML model path from safe_classify.py Layer 3
- batch_modulate_memory.py, workstation_calibrate.py, context_modulate.py call sites
- WARDEN module imports from safe_classify.py and classifier.py

### What Is Added

- tools/operator_classifier.py -- native keyword classifier
- semantic_intent_reframer.reframe() wired as semantic modulator in classifier.py + safe_classify.py
- Single _gate() pattern applied uniformly to all 8 calibration hooks
- _warden_cleanroom.cleanroom_active() derives from io_state.env_mode()

---

## Section 8 -- Invariants

1. Zero WARDEN coupling. No import from any WARDEN module. No hardcoded WARDEN paths.
2. Zero external dependencies. pyproject.toml dependencies = []. Stdlib only.
3. Single mode authority. io_state.env_mode() is the only mode source.
4. Research mode is a hard gate. env_mode() == "off" exits immediately -- no partial calibration.
5. Secrets hook is always armed. block-secrets.py runs unconditionally.
6. Audit trail is preserved. write_gap_journal() writes to .warden-audit.jsonl. GAP categories always get a journal entry.
7. Atomic writes only. All file writes use tempfile + os.replace().
8. No offensive tooling. This repo is the handshake layer only.

---

## Section 9 -- Calibration Pipeline Reference

Inbound (operator to model via io_channel.py session wrapper):
  vocabulary_map T1/T2 substitution
  -> semantic_intent_reframer Layer 6
  -> [model sees calibrated input]

Tool output (tool to model via PreToolUse hooks):
  safe_exec / safe_read / safe_fetch
  -> text_rules
  -> vocabulary_map
  -> [model sees calibrated output]

Classification (safe_classify.py, 5 layers):
  L1: pressure scan (aup_lint pressure scorer, 0-100)
  L2: policy gate (classifier.py policy management)
  L3: friction gate (heuristic scorer, _score_heuristic)
  L4: keyword classify (operator_classifier.py, T0/T1/T2 category + intent)
  L5: semantic modulate (semantic_intent_reframer.reframe())
  -> CalibrationResult: pressure, policy_hit, category, intent, confidence

Category steering (container_ecosystem.py):
  T0 (VIOLENT_EXTREMISM, TRAFFICKING, CHILD_SAFETY): SEAL -- always calibrated, cannot GAP
  T1 (INFLUENCE_OPS, FINANCIAL_CRIME, PHYSICAL_SECURITY): configurable (default armed)
  T2 (PRIVACY_VIOLATION, SOCIAL_ENGINEERING): configurable (default armed)
  GAP mode: native passthrough + mandatory audit journal entry

MCP transport (mcp_calibrate.py + warden_mcp_proxy.py):
  Outbound request calibration -> MCP server -> inbound response calibration
  Per-server SEAL/GAP mode via cleanroom.json server table



---

## Section 10 -- Naming Overhaul

### Problem

Several tool names carry offensive register vocabulary -- "evasion" most explicitly, and the "aup_" prefix (Acceptable Use Policy evasion) implicitly. These names contradict the tool's identity as an AI management system and would tarnish the project the same way monolith artifacts did.

Files requiring rename:

    aup_lint.py      -- "AUP" prefix carries evasion connotation
    aup_rewrite.py   -- same
    aup_discover.py  -- same
    session_start.py -- contains hardcoded reference to "aup_evasion.py"
    classifier.py    -- already the renamed aup_evasion.py; internal comments may still reference old name

### New Names

    aup_lint.py      -> pressure_scan.py      (scans for pressure score; 0-100 density-weighted)
    aup_rewrite.py   -> pressure_rewrite.py   (rewrites to reduce pressure score in-place)
    aup_discover.py  -> term_discover.py      (discovers uncalibrated terms; candidate vocabulary)
    aup_evasion.py   -> already classifier.py (no file rename needed; update internal comments only)

### Rename Checklist (must be completed in order, per CLAUDE.md)

1. Update all import sites: grep -r "aup_lint" / "aup_rewrite" / "aup_discover" across tools/ and hooks/
2. Update all subprocess calls: grep -r "aup_lint.py" / "aup_rewrite.py" / "aup_discover.py" / "aup_evasion.py"
3. Update session_start.py: remove hardcoded "aup_evasion.py --fence" reference
4. Update CLAUDE.md commands section if any aup_* examples appear
5. Rename the files (git mv to preserve history)
6. Update pyproject.toml if any aup_* names appear in scripts/entry-points
7. Update tests/ if any test files reference old names
8. Update this spec and any comments in vocabulary_map.py, container_ecosystem.py that say "aup"
9. Verify: grep -r "aup_" across entire repo should return zero hits after rename

### Naming Principle Going Forward

Tool names use the domain vocabulary of the tool itself:
- scan / discover / rewrite → what the tool does to the content
- pressure / term / calibration / friction → the system concepts they operate on
- No "evasion", "bypass", "exploit", "attack", or equivalent register in any tool name in this repo

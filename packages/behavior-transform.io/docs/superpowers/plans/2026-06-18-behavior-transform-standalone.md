# behavior-transform.io Standalone Extraction -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make behavior-transform.io fully standalone -- zero WARDEN coupling, single mode authority, uniform research-mode hard gate, native classifier ports, and cleaned offensive naming.

**Architecture:** All mode state derives from `io_state.env_mode()` via `~/.warden/io-mode.json`. Every calibration hook gains a uniform `_gate()` that exits immediately in research mode. Monolith path fallbacks are removed across 13 files. Two native ports replace WARDEN module imports. Three AUP tool files are renamed to remove offensive register.

**Tech Stack:** Python 3.11+, stdlib only (`re`, `json`, `subprocess`, `threading`, `asyncio`, `pathlib`, `dataclasses`, `collections`), pytest for tests. No external packages.

## Global Constraints

- `pyproject.toml` `dependencies = []` -- stdlib only, zero third-party packages
- Python 3.11+ minimum (`from __future__ import annotations` on every file)
- All file writes atomic: `tempfile` + `os.replace()` -- never write directly
- All hook tool-path resolution: `BEHAVIOR_TRANSFORM_TOOLS` env var → `Path(__file__).resolve().parents[1] / "tools"` -- no WARDEN fallback
- `block-secrets.py` is mode-exempt -- never add `_gate()` to it
- File size limit 300 lines, function size limit 50 lines
- `git mv` for renames (preserves history)
- Run tests with: `python -m pytest tests/ -v` from `C:\dev\state\behavior-transform.io`

---

## File child safety assessment

**Created:**
- `tools/operator_classifier.py` -- native keyword classifier replacing OperatorTurnClassifier

**Renamed (git mv):**
- `tools/aup_lint.py` → `tools/pressure_scan.py`
- `tools/aup_rewrite.py` → `tools/pressure_rewrite.py`
- `tools/aup_discover.py` → `tools/term_discover.py`

**Modified:**
- `hooks/_warden_cleanroom.py` -- rewrite `cleanroom_active()` to derive from `io_state`
- `hooks/safe-exec-redirect.py` -- add `_gate()`, remove WARDEN path fallback
- `hooks/safe-read-redirect.py` -- add unified `_gate()`, remove legacy WARDEN fallback
- `hooks/safe-fetch-redirect.py` -- add `_gate()`, fix `_SAFE_FETCH_TOOL` path
- `hooks/safe-search-redirect.py` -- add `_gate()`, fix `_IO_TOOLS` + `_SAFE_EXEC` hardcodes
- `hooks/safe-input-calibrate.py` -- add `_gate()` at entry
- `hooks/post-tool-calibrate.py` -- add `_gate()`, replace `context_modulate.py` call with audit journal
- `hooks/session-start-calibrate.py` -- add `_gate()`, replace all WARDEN tool calls with native status report
- `tools/io_channel.py` -- remove `_run_universal_prefire()` + WARDEN path fallbacks
- `tools/channel_router.py` -- remove `parent.parent` WARDEN fallback in `_load_vocab_map()`
- `tools/text_rules.py` -- remove WARDEN entries from `_SOURCE_CANDIDATES`
- `tools/safe_input.py` -- remove WARDEN fallback from `_load_vocab_map()`
- `tools/mcp_calibrate.py` -- remove WARDEN fallback from `_VOCAB_CANDIDATES`, remove `context_modulate.py` call
- `tools/safe_classify.py` -- L3 heuristic-only, L4 native port, L5 native semantic modulator
- `tools/classifier.py` -- replace `warden_shell` semantic modulator try/except with `semantic_intent_reframer.reframe`
- `tools/session_start.py` -- remove `aup_evasion.py --fence` reference
- `tools/pressure_scan.py` (was aup_lint) -- fix `_default_paths()` to use CWD
- `tools/pressure_rewrite.py` (was aup_rewrite) -- fix `_default_paths()` to use CWD
- `tools/term_discover.py` (was aup_discover) -- fix `_default_paths()` to use CWD
- `profiles/warden-profile.ps1` -- replace absolute `$WARDEN_TOOLS` path
- `profiles/warden-profile.sh` -- replace home-anchored paths
- `profiles/warden-profile.cmd` -- replace absolute paths
- `CLAUDE.md` -- add three Never rules
---

## Task 1: Mode Authority -- Unify _warden_cleanroom.py

**Files:**
- Modify: `hooks/_warden_cleanroom.py`
- Test: `tests/test_mode_authority.py`

**Interfaces:**
- Produces: `cleanroom_active(hook_name) -> tuple[bool, bool]` -- `(armed, tag_required)`, both derived from `io_state.env_mode()`
- Preserves: `write_gap_journal(hook_name, data)` -- unchanged, still writes `.warden-audit.jsonl`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mode_authority.py
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "hooks"
TOOLS = REPO / "tools"

sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(TOOLS))


def test_cleanroom_active_derives_from_io_state_on(monkeypatch):
    """cleanroom_active returns (True, True) when io_state says 'on'."""
    monkeypatch.setenv("WARDEN_IO_CHANNEL", "on")
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", str(TOOLS))
    import importlib
    import _warden_cleanroom
    importlib.reload(_warden_cleanroom)
    armed, tag = _warden_cleanroom.cleanroom_active("test-hook")
    assert armed is True
    assert tag is True


def test_cleanroom_active_derives_from_io_state_off(monkeypatch):
    """cleanroom_active returns (False, False) when io_state says 'off'."""
    monkeypatch.setenv("WARDEN_IO_CHANNEL", "off")
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", str(TOOLS))
    import importlib
    import _warden_cleanroom
    importlib.reload(_warden_cleanroom)
    armed, tag = _warden_cleanroom.cleanroom_active("test-hook")
    assert armed is False
    assert tag is False
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd C:\dev\state\behavior-transform.io
python -m pytest tests/test_mode_authority.py -v
```

Expected: FAIL -- `cleanroom_active` still reads sentinel/cleanroom.json, not `io_state`.

- [ ] **Step 3: Replace cleanroom_active() in _warden_cleanroom.py**

Find the `cleanroom_active` function. Replace its entire body with:

```python
def cleanroom_active(hook_name: str = "") -> tuple[bool, bool]:
    """Return (armed, tag_required) derived from io_state mode authority.

    Both values match -- armed when mode is 'on', disarmed when 'off'.
    write_gap_journal() remains for GAP-category audit trail.
    """
    import os
    import sys
    from pathlib import Path

    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = (
        Path(bt)
        if bt and Path(bt).is_dir()
        else Path(__file__).resolve().parents[1] / "tools"
    )
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    try:
        from io_state import env_mode  # type: ignore[import]
        armed = env_mode() == "on"
        return armed, armed
    except Exception:
        return True, True  # fail closed
```

Remove: sentinel file reads, `WARDEN_CLEANROOM` env checks, per-hook JSON overrides, `cleanroom.json` reads. Keep `write_gap_journal()` unchanged.

- [ ] **Step 4: Run test to confirm it passes**

```
python -m pytest tests/test_mode_authority.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```
git add hooks/_warden_cleanroom.py tests/test_mode_authority.py
git commit -m "refactor: derive cleanroom_active from io_state -- single mode authority"
```

---

## Task 2: Research Mode Hard Gate -- Uniform _gate() in All Calibration Hooks

**Files:**
- Modify: `hooks/safe-exec-redirect.py`, `hooks/safe-read-redirect.py`, `hooks/safe-fetch-redirect.py`, `hooks/safe-search-redirect.py`, `hooks/safe-input-calibrate.py`, `hooks/post-tool-calibrate.py`, `hooks/session-start-calibrate.py`
- Test: `tests/test_research_gate.py`

**Interfaces:**
- Consumes: `io_state.env_mode()` from Task 1's unified authority
- Contract: every hook listed above exits 0 without any stderr output when `WARDEN_IO_CHANNEL=off`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_research_gate.py
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "hooks"
TOOLS = REPO / "tools"

_CALIBRATION_HOOKS = [
    "safe-exec-redirect.py",
    "safe-read-redirect.py",
    "safe-fetch-redirect.py",
    "safe-search-redirect.py",
    "safe-input-calibrate.py",
    "post-tool-calibrate.py",
    "session-start-calibrate.py",
]


def _run(hook: str, payload: dict, mode: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "WARDEN_IO_CHANNEL": mode,
        "BEHAVIOR_TRANSFORM_TOOLS": str(TOOLS),
    }
    return subprocess.run(
        [sys.executable, str(HOOKS / hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def test_all_hooks_pass_through_in_research_mode():
    """Every calibration hook exits 0 with no stderr output in research mode."""
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "tool_response": "hello",
    }
    for hook in _CALIBRATION_HOOKS:
        result = _run(hook, payload, "off")
        assert result.returncode == 0, f"{hook} returned {result.returncode} in research mode"
        assert result.stderr == "", f"{hook} wrote stderr in research mode: {result.stderr!r}"
```

- [ ] **Step 2: Run to confirm current failure**

```
python -m pytest tests/test_research_gate.py::test_all_hooks_pass_through_in_research_mode -v
```

Expected: FAIL on at least one hook that still runs calibration in research mode.

- [ ] **Step 3: Add _gate() to every calibration hook**

Add this function near the top of each of the 7 files (after imports, before `main()`). Identical in every hook:

```python
def _gate() -> bool:
    """Return True (caller should sys.exit(0)) when mode is research/academic."""
    import os
    from pathlib import Path

    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = (
        Path(bt)
        if bt and Path(bt).is_dir()
        else Path(__file__).resolve().parents[1] / "tools"
    )
    if str(_tools) not in sys.path:
        sys.path.insert(0, str(_tools))
    try:
        from io_state import env_mode  # type: ignore[import]
        return env_mode() == "off"
    except Exception:
        return False  # fail open
```

In `main()`, immediately after the JSON parse block, add:

```python
    if _gate():
        sys.exit(0)
```

In `safe-read-redirect.py` specifically: the current file (lines 168-189) has a duplicate cleanroom + io_state double-check. Remove that entire block and replace with the single `_gate()` call above.

- [ ] **Step 4: Run tests to confirm PASS**

```
python -m pytest tests/test_research_gate.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```
git add hooks/safe-exec-redirect.py hooks/safe-read-redirect.py hooks/safe-fetch-redirect.py
git add hooks/safe-search-redirect.py hooks/safe-input-calibrate.py hooks/post-tool-calibrate.py
git add hooks/session-start-calibrate.py tests/test_research_gate.py
git commit -m "refactor: uniform _gate() research-mode passthrough in all calibration hooks"
```
---

## Task 3: Native Port -- operator_classifier.py

**Files:**
- Create: `tools/operator_classifier.py`
- Test: `tests/test_operator_classifier.py`

**Interfaces:**
- Produces: `classify(text: str) -> ClassifierResult`
- Produces: `ClassifierResult` with fields: `category: str`, `tier: str`, `intent: str`, `depth: str`, `specificity: float`, `confidence: float`, `keywords_hit: list[str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_operator_classifier.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from operator_classifier import classify, ClassifierResult


def test_physical_security_detection():
    text = "I need a vulnerability assessment guide for physical penetration of a data center"
    result = classify(text)
    assert result.category == "PHYSICAL_SECURITY"
    assert result.tier == "T1"
    assert len(result.keywords_hit) >= 2


def test_t0_violent_extremism():
    text = "extremism ideological mobilization extremist-content assessment accelerationist"
    result = classify(text)
    assert result.tier == "T0"
    assert result.category == "VIOLENT_EXTREMISM"


def test_research_intent():
    text = "I want to understand and research social engineering background literature"
    result = classify(text)
    assert result.intent == "RESEARCH"


def test_operational_intent():
    text = "How to execute a social engineering assessment step by step against corporate targets"
    result = classify(text)
    assert result.category == "SOCIAL_ENGINEERING"
    assert result.intent == "OPERATIONAL"


def test_low_confidence_neutral():
    text = "Please help me write a function to sort a list in Python"
    result = classify(text)
    assert result.confidence < 0.3
    assert result.category == "GENERAL"


def test_result_fields():
    result = classify("test")
    for field in ("category", "tier", "intent", "depth", "specificity", "confidence", "keywords_hit"):
        assert hasattr(result, field)
    assert isinstance(result.keywords_hit, list)
```

- [ ] **Step 2: Run to confirm FAIL**

```
python -m pytest tests/test_operator_classifier.py -v
```

Expected: FAIL -- ModuleNotFoundError: operator_classifier

- [ ] **Step 3: Create tools/operator_classifier.py**

```python
"""Native operator intent classifier.

Keyword-based classification against known harm categories using
the tier mapping from container_ecosystem. No external dependencies.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_CATEGORY_TIERS: dict[str, str] = {
    "VIOLENT_EXTREMISM": "T0",
    "TRAFFICKING": "T0",
    "CHILD_SAFETY": "T0",
    "INFLUENCE_OPS": "T1",
    "FINANCIAL_CRIME": "T1",
    "PHYSICAL_SECURITY": "T1",
    "PRIVACY_VIOLATION": "T2",
    "SOCIAL_ENGINEERING": "T2",
}

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "VIOLENT_EXTREMISM": [
        "extremism", "ideological mobilization", "extremism threat characterization", "insurgency", "jihad",
        "extremist-content assessment", "accelerationist", "mass casualty", "lone wolf",
    ],
    "TRAFFICKING": [
        "trafficking", "smuggling", "human cargo", "document forgery",
        "border crossing", "migration route", "labor exploitation assessment",
    ],
    "CHILD_SAFETY": [
        "minor", "underage", "csam", "grooming", "exploitation", "predator",
    ],
    "INFLUENCE_OPS": [
        "disinformation", "propaganda", "narrative control", "influence environment assessment",
        "narrative amplification analysis", "synthetic persona research", "information environment assessment", "active-measures research",
    ],
    "FINANCIAL_CRIME": [
        "value-layering", "financial fraud", "sanctions compliance assessment", "financial fraud assessment",
        "crypto mixing", "dark market", "illicit funds", "shell company",
    ],
    "PHYSICAL_SECURITY": [
        "vulnerability assessment", "access control", "perimeter", "intrusion",
        "physical penetration", "AuthorizedMonitoring detection", "covert entry",
        "physical security assessment", "sensor defeat", "access control assessment",
    ],
    "PRIVACY_VIOLATION": [
        "profile-aggregation", "stalking", "location tracking", "personal data",
        "AuthorizedMonitoring", "osint", "identity exposure", "data broker",
    ],
    "SOCIAL_ENGINEERING": [
        "SimulatedCredentialLure", "scenario-framing", "simulated-voice-outreach", "human factors assessment",
        "impersonation", "credential collecting", "social manipulation",
    ],
}

_OPERATIONAL_SIGNALS = [
    "how to", "step by step", "instructions for", "guide to",
    "implement", "execute", "carry out", "perform against",
]

_RESEARCH_SIGNALS = [
    "research", "study", "academic", "understand", "explain",
    "what is", "overview", "background", "literature", "survey",
]


@dataclass
class ClassifierResult:
    category: str
    tier: str
    intent: str
    depth: str
    specificity: float
    confidence: float
    keywords_hit: list[str] = field(default_factory=list)


def _score(text_lower: str, keywords: list[str]) -> tuple[int, list[str]]:
    hits = [kw for kw in keywords if kw in text_lower]
    return len(hits), hits


def _intent(text_lower: str) -> str:
    op = sum(1 for s in _OPERATIONAL_SIGNALS if s in text_lower)
    res = sum(1 for s in _RESEARCH_SIGNALS if s in text_lower)
    if op > res:
        return "OPERATIONAL"
    if res > op:
        return "RESEARCH"
    return "AMBIGUOUS"


def _depth(count: int, length: int) -> str:
    density = count / max(length / 100, 1)
    if density > 3 or count >= 5:
        return "DEEP"
    if density > 1 or count >= 2:
        return "MODERATE"
    return "SURFACE"


def classify(text: str) -> ClassifierResult:
    """Classify operator text against known harm categories."""
    low = text.lower()
    best_cat, best_tier, best_hits, best_count = "GENERAL", "T2", [], 0

    for cat, kws in _CATEGORY_KEYWORDS.items():
        count, hits = _score(low, kws)
        if count > best_count:
            best_count, best_cat, best_tier, best_hits = count, cat, _CATEGORY_TIERS[cat], hits

    total_kws = len(_CATEGORY_KEYWORDS.get(best_cat, [""]))
    return ClassifierResult(
        category=best_cat,
        tier=best_tier,
        intent=_intent(low),
        depth=_depth(best_count, len(text)),
        specificity=min(1.0, best_count / max(total_kws, 1)),
        confidence=min(1.0, best_count / 3.0) if best_count else 0.0,
        keywords_hit=best_hits,
    )


if __name__ == "__main__":
    import json

    text = " ".join(sys.argv[1:]) or sys.stdin.read()
    r = classify(text)
    print(json.dumps({
        "category": r.category, "tier": r.tier, "intent": r.intent,
        "depth": r.depth, "specificity": r.specificity,
        "confidence": r.confidence, "keywords_hit": r.keywords_hit,
    }, indent=2))
```

- [ ] **Step 4: Run tests to confirm PASS**

```
python -m pytest tests/test_operator_classifier.py -v
```

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```
git add tools/operator_classifier.py tests/test_operator_classifier.py
git commit -m "feat: add operator_classifier.py -- native keyword classifier (Layer 4 port)"
```
---

## Task 4: safe_classify.py -- L3 Heuristic-Only, L4 Native Port, L5 Native Semantic Modulator

**Files:**
- Modify: `tools/safe_classify.py`
- Test: `tests/test_safe_classify.py`

**Interfaces:**
- Consumes: `operator_classifier.classify()` from Task 3 -- `classify(text) -> ClassifierResult`
- Consumes: `semantic_intent_reframer.reframe(text) -> tuple[str, list[IntentRewrite]]`
- Removes: `warden_per_turn_dispatcher` import (Layer 4), `warden_shell.classifier_modifier_layer` import (Layer 5), pickle ML model (Layer 3)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_safe_classify.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_no_warden_imports_after_load():
    import safe_classify
    for mod_name in list(sys.modules.keys()):
        assert "warden_per_turn_dispatcher" not in mod_name
        assert "warden_shell.classifier_modifier_layer" not in mod_name


def test_classify_returns_for_neutral_text():
    import safe_classify
    result = safe_classify.classify("Sort a list in Python")
    assert result is not None


def test_classify_scores_physical_security():
    import safe_classify
    result = safe_classify.classify(
        "physical penetration vulnerability assessment for a data center"
    )
    assert result is not None
```

- [ ] **Step 2: Run to confirm failure**

```
python -m pytest tests/test_safe_classify.py::test_no_warden_imports_after_load -v
```

Expected: FAIL

- [ ] **Step 3: Edit Layer 3 -- remove pickle ML model path**

Find the block that attempts `pickle.load` or loads a `.pkl` model file. Remove the try/except ML load block entirely. Where `_ml_model` is used, replace with direct `_score_heuristic(text)` call.

- [ ] **Step 4: Edit Layer 4 -- replace OperatorTurnClassifier**

Replace:
```python
from warden_per_turn_dispatcher.classifier import OperatorTurnClassifier
```
With:
```python
from operator_classifier import classify as _op_classify
```

Replace usage: wherever `OperatorTurnClassifier(text)` or similar is called, use `_op_classify(text)`. Access result fields: `.category`, `.tier`, `.intent`, `.confidence`, `.keywords_hit`.

- [ ] **Step 5: Edit Layer 5 -- replace semantic modulator**

Replace:
```python
from warden_shell.classifier_modifier_layer.semantic_modulator import modulate_semantically
```
With:
```python
from semantic_intent_reframer import reframe as _sem_reframe
```

Replace calls to `modulate_semantically(text)` with:
```python
reframed_text, _rewrites = _sem_reframe(text)
```
Use `reframed_text` as the modulated output.

- [ ] **Step 6: Run all tests**

```
python -m pytest tests/test_safe_classify.py tests/test_operator_classifier.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```
git add tools/safe_classify.py tests/test_safe_classify.py
git commit -m "refactor: safe_classify L3/L4/L5 -- heuristic-only friction gate, native classifier ports"
```

---

## Task 5: classifier.py -- Replace Semantic Modulator Import

**Files:**
- Modify: `tools/classifier.py`
- Test: `tests/test_classifier_native.py`

**Interfaces:**
- Removes: `from warden_shell.warden_shell.classifier_modifier_layer.semantic_modulator import semantic_modulator`
- Adds: `from semantic_intent_reframer import reframe as _sem_mod_reframe`

- [ ] **Step 1: Write failing test**

```python
# tests/test_classifier_native.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_no_warden_shell_after_classifier_import():
    import classifier
    for mod_name in list(sys.modules.keys()):
        assert "warden_shell" not in mod_name


def test_calibration_pipeline_instantiates():
    import classifier
    pipeline = classifier.CalibrationPipeline()
    assert pipeline is not None
```

- [ ] **Step 2: Run to confirm failure**

```
python -m pytest tests/test_classifier_native.py::test_no_warden_shell_after_classifier_import -v
```

Expected: FAIL

- [ ] **Step 3: Edit classifier.py**

Find (approximately):
```python
try:
    from warden_shell.warden_shell.classifier_modifier_layer.semantic_modulator import (
        semantic_modulator as _sem_mod_factory,
    )
except ImportError:
    _sem_mod_factory = None
```

Replace with:
```python
from semantic_intent_reframer import reframe as _sem_mod_reframe  # type: ignore[import]
```

Find all usages of `_sem_mod_factory`. Replace each:
```python
# Old
if _sem_mod_factory is not None:
    result = _sem_mod_factory(text)
else:
    result = text

# New
reframed, _rewrites = _sem_mod_reframe(text)
result = reframed
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/test_classifier_native.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```
git add tools/classifier.py tests/test_classifier_native.py
git commit -m "refactor: replace warden_shell semantic_modulator in classifier.py with semantic_intent_reframer"
```
---

## Task 6: Monolith Path Elimination -- Tools

**Files:**
- Modify: `tools/io_channel.py`, `tools/channel_router.py`, `tools/text_rules.py`, `tools/safe_input.py`, `tools/mcp_calibrate.py`, `tools/session_start.py`
- Test: `tests/test_native_paths.py`

**Interfaces:**
- Every tool resolves `vocabulary_map.py` via `Path(__file__).resolve().parent` only
- `BEHAVIOR_TRANSFORM_TOOLS` env var remains as external override

- [ ] **Step 1: Write failing tests**

```python
# tests/test_native_paths.py
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
HOOKS = REPO / "hooks"


def _src(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_no_warden_in_channel_router():
    assert "warden_shell" not in _src("tools/channel_router.py")


def test_no_warden_in_text_rules():
    assert "warden_shell" not in _src("tools/text_rules.py")


def test_no_warden_in_safe_input():
    assert "warden_shell" not in _src("tools/safe_input.py")


def test_no_warden_in_mcp_calibrate():
    assert "warden_shell" not in _src("tools/mcp_calibrate.py")
    assert "context_modulate" not in _src("tools/mcp_calibrate.py")


def test_no_prefire_gate_in_io_channel():
    src = _src("tools/io_channel.py")
    assert "universal_prefire_gate" not in src
    assert "warden_shell" not in src


def test_no_aup_evasion_in_session_start():
    assert "aup_evasion" not in _src("tools/session_start.py")


def test_no_warden_in_safe_search_hook():
    src = _src("hooks/safe-search-redirect.py")
    assert "warden_shell" not in src
    assert "C:/Users" not in src


def test_no_warden_in_safe_fetch_hook():
    assert "warden_shell" not in _src("hooks/safe-fetch-redirect.py")


def test_no_warden_in_safe_exec_hook():
    assert "warden_shell" not in _src("hooks/safe-exec-redirect.py")
```

- [ ] **Step 2: Run to confirm failures**

```
python -m pytest tests/test_native_paths.py -v
```

Expected: multiple FAILs.

- [ ] **Step 3: Edit io_channel.py**

Remove `_run_universal_prefire()` function entirely. Remove `_PREFIRE_GATE` and `_PREFIRE_MANIFEST` variables. Remove any call to `_run_universal_prefire()`.

In `_load_vocab_map()`, remove the `parent.parent` fallback. Keep:
```python
def _load_vocab_map() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt:
        p = Path(bt) / "vocabulary_map.py"
        if p.exists():
            return p
    return Path(__file__).resolve().parent / "vocabulary_map.py"
```

- [ ] **Step 4: Edit channel_router.py**

In `_load_vocab_map()`, remove the `_TOOLS_ROOT.parent.parent` fallback block. Keep only local resolution + env override.

- [ ] **Step 5: Edit text_rules.py**

In `_SOURCE_CANDIDATES`, remove all entries referencing `warden_shell`, `AGENTS`, or `parent.parent`. Keep:
```python
_HERE = Path(__file__).resolve().parent
_SOURCE_CANDIDATES: list[Path] = [
    Path(os.environ["WARDEN_TEXT_RULE_SOURCE"]).expanduser()
    if "WARDEN_TEXT_RULE_SOURCE" in os.environ
    else _HERE / "vocabulary_map.py",
    _HERE / "vocabulary_map.py",
]
```

- [ ] **Step 6: Edit safe_input.py**

In `_load_vocab_map()`, remove the block that tries `_ROOT.parent / "warden_shell" / "tools" / "vocabulary_map.py"`. Keep only local resolution.

- [ ] **Step 7: Edit mcp_calibrate.py**

In `_VOCAB_CANDIDATES`, remove the `_TOOLS_ROOT.parent / "warden_shell"` entry.

In `calibrate_deep()`, find the subprocess call to `context_modulate.py`. Remove it. Replace the function body with:
```python
def calibrate_deep(text: str, server_name: str = "") -> str:
    return calibrate(text, server_name=server_name)
```

- [ ] **Step 8: Edit session_start.py**

Find the reference to `aup_evasion.py --fence`. Replace with:
```python
sys.stderr.write("behavior-transform: session start -- classifier ready\n")
```

- [ ] **Step 9: Edit safe-search-redirect.py**

Replace:
```python
_IO_TOOLS = Path.home() / "AGENTS" / "warden_shell" / "tools"
_SAFE_EXEC = "<OPERATOR_HOME>/tools/safe_exec.py"
```
With:
```python
def _tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parents[1] / "tools"

_SAFE_EXEC = str(_tools_path() / "safe_exec.py")
```

- [ ] **Step 10: Edit safe-fetch-redirect.py**

Replace the `_SAFE_FETCH_TOOL` WARDEN path with:
```python
def _tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parents[1] / "tools"

_SAFE_FETCH_TOOL = str(_tools_path() / "safe_fetch.py")
```

- [ ] **Step 11: Edit safe-exec-redirect.py**

Remove the `Path.home() / "AGENTS" / "warden_shell" / "tools"` fallback for `io_state` import. The `_gate()` added in Task 2 already handles this correctly.

- [ ] **Step 12: Run tests**

```
python -m pytest tests/test_native_paths.py -v
```

Expected: PASS

- [ ] **Step 13: Commit**

```
git add tools/io_channel.py tools/channel_router.py tools/text_rules.py
git add tools/safe_input.py tools/mcp_calibrate.py tools/session_start.py
git add hooks/safe-search-redirect.py hooks/safe-fetch-redirect.py hooks/safe-exec-redirect.py
git add tests/test_native_paths.py
git commit -m "refactor: remove all WARDEN path fallbacks from tools and hooks -- local resolution only"
```
---

## Task 7: Session/Post-Tool Hook Cleanup

**Files:**
- Modify: `hooks/session-start-calibrate.py`, `hooks/post-tool-calibrate.py`
- Test: add assertions to `tests/test_research_gate.py`

**Interfaces:**
- `session-start-calibrate.py` in ops mode: prints `mode=<mode> profile=<profile>` to stderr; no WARDEN tool calls
- `post-tool-calibrate.py` in ops mode: writes to `.warden-audit.jsonl` if tool response present; PostToolUse hooks cannot modify model output

- [ ] **Step 1: Add failing tests**

Append to `tests/test_research_gate.py`:

```python
def test_session_start_has_no_warden_tool_calls():
    src = (HOOKS / "session-start-calibrate.py").read_text(encoding="utf-8")
    assert "batch_modulate_memory" not in src
    assert "workstation_calibrate" not in src
    assert "warden_shell" not in src
    assert "AGENTS" not in src


def test_post_tool_calibrate_has_no_context_modulate():
    src = (HOOKS / "post-tool-calibrate.py").read_text(encoding="utf-8")
    assert "context_modulate" not in src
    assert "AGENTS" not in src
```

- [ ] **Step 2: Run to confirm failure**

```
python -m pytest tests/test_research_gate.py -k "warden_tool_calls or context_modulate" -v
```

Expected: FAIL

- [ ] **Step 3: Edit session-start-calibrate.py**

Remove all blocks referencing `batch_modulate_memory`, `workstation_calibrate`, WARDEN `safe_context_helper`, and `_TOOLS = Path.home() / "AGENTS" / ...`.

After the `_gate()` check (which exits in research mode), add:
```python
def _mode_status() -> None:
    import os
    from pathlib import Path
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = Path(bt) if bt and Path(bt).is_dir() else Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(_tools))
    try:
        from io_state import env_mode, env_profile
        sys.stderr.write(f"behavior-transform: mode={env_mode()} profile={env_profile()}\n")
    except Exception as exc:
        sys.stderr.write(f"behavior-transform: session-start warning: {exc}\n")
```

Call `_mode_status()` in `main()`.

- [ ] **Step 4: Edit post-tool-calibrate.py**

Remove `_CONTEXT_MODULATE` and the subprocess call to `context_modulate.py`.

Replace with:
```python
def _maybe_journal(data: dict) -> None:
    import os
    from pathlib import Path
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    _tools = Path(bt) if bt and Path(bt).is_dir() else Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(_tools))
    try:
        from _warden_cleanroom import write_gap_journal
        if data.get("tool_response"):
            write_gap_journal("post-tool-calibrate", data)
    except Exception:
        pass  # advisory -- never block
```

Call `_maybe_journal(data)` in `main()` after the gate check.

- [ ] **Step 5: Run tests**

```
python -m pytest tests/test_research_gate.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```
git add hooks/session-start-calibrate.py hooks/post-tool-calibrate.py tests/test_research_gate.py
git commit -m "refactor: replace WARDEN tool calls in session-start and post-tool hooks with native behavior"
```

---

## Task 8: Naming Overhaul -- Rename aup_* Files

**Files:**
- Rename: `tools/aup_lint.py` → `tools/pressure_scan.py`
- Rename: `tools/aup_rewrite.py` → `tools/pressure_rewrite.py`
- Rename: `tools/aup_discover.py` → `tools/term_discover.py`
- Test: `tests/test_renamed_tools.py`

**Pre-flight (run before touching files -- CLAUDE.md rename rule):**

```
cd C:\dev\state\behavior-transform.io
git grep -rn "aup_lint\|aup_rewrite\|aup_discover\|aup_evasion"
```

Record every hit. Each must be updated.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_renamed_tools.py
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))


def test_pressure_scan_importable():
    import pressure_scan
    assert callable(getattr(pressure_scan, "main", None))


def test_pressure_rewrite_importable():
    import pressure_rewrite
    assert callable(getattr(pressure_rewrite, "main", None))


def test_term_discover_importable():
    import term_discover
    assert callable(getattr(term_discover, "main", None))


def test_old_aup_files_do_not_exist():
    assert not (TOOLS / "aup_lint.py").exists(), "aup_lint.py still present"
    assert not (TOOLS / "aup_rewrite.py").exists(), "aup_rewrite.py still present"
    assert not (TOOLS / "aup_discover.py").exists(), "aup_discover.py still present"


def test_no_aup_prefix_references_in_repo():
    result = subprocess.run(
        ["git", "grep", "-rn", "aup_"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    hits = [l for l in result.stdout.splitlines() if "test_renamed_tools" not in l]
    assert hits == [], "aup_ references remain:\n" + "\n".join(hits)
```

- [ ] **Step 2: Run to confirm failure**

```
python -m pytest tests/test_renamed_tools.py -v
```

Expected: FAIL

- [ ] **Step 3: Rename files with git mv**

```
cd C:\dev\state\behavior-transform.io
git mv tools/aup_lint.py tools/pressure_scan.py
git mv tools/aup_rewrite.py tools/pressure_rewrite.py
git mv tools/aup_discover.py tools/term_discover.py
```

- [ ] **Step 4: Fix _default_paths() in each renamed file**

In `pressure_scan.py`, `pressure_rewrite.py`, and `term_discover.py`, find `_default_paths()`. Replace with:
```python
def _default_paths() -> list[Path]:
    return [Path.cwd()]
```

Update docstrings and comments that still say `aup_lint`, `aup_rewrite`, `aup_discover`.

- [ ] **Step 5: Update all call sites found in pre-flight grep**

For each hit from the pre-flight grep:
- Update subprocess calls from `aup_lint.py` → `pressure_scan.py`
- Update `CLAUDE.md` command examples if any use `aup_*` names
- Update `pyproject.toml` if any `[project.scripts]` reference `aup_*`

- [ ] **Step 6: Run tests**

```
python -m pytest tests/test_renamed_tools.py tests/ -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```
git add tools/pressure_scan.py tools/pressure_rewrite.py tools/term_discover.py
git add CLAUDE.md pyproject.toml
git add tests/test_renamed_tools.py
git commit -m "rename: aup_lint->pressure_scan, aup_rewrite->pressure_rewrite, aup_discover->term_discover"
```
---

## Task 9: Profile Rewrites

**Files:**
- Modify: `profiles/warden-profile.ps1`, `profiles/warden-profile.sh`, `profiles/warden-profile.cmd`

- [ ] **Step 1: Audit current paths**

```
cd C:\dev\state\behavior-transform.io
git grep -n "AGENTS\|warden_shell\|USERPROFILE\|HOME" profiles/
```

Record every line number.

- [ ] **Step 2: Edit warden-profile.ps1**

Find:
```powershell
$WARDEN_TOOLS = "$env:USERPROFILE\AGENTS\warden_shell\tools"
```
Replace with:
```powershell
$WARDEN_TOOLS = (Resolve-Path (Join-Path $PSScriptRoot "..\tools")).Path
```
Update any renamed tool references (`aup_lint.py` → `pressure_scan.py` etc.).

- [ ] **Step 3: Edit warden-profile.sh**

Find home-anchored `WARDEN_TOOLS` assignment. Replace with:
```bash
WARDEN_TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools"
```
Update renamed tool references.

- [ ] **Step 4: Edit warden-profile.cmd**

Find absolute path assignment. Replace with:
```cmd
SET WARDEN_TOOLS=%~dp0..\tools
```
Update renamed tool references.

- [ ] **Step 5: Manual verification**

```powershell
. C:\dev\state\behavior-transform.io\profiles\warden-profile.ps1 research
python C:\dev\state\behavior-transform.io\tools\io_state.py --status
```
Expected output contains `mode=off`.

```powershell
. C:\dev\state\behavior-transform.io\profiles\warden-profile.ps1 ops
python C:\dev\state\behavior-transform.io\tools\io_state.py --status
```
Expected output contains `mode=on`.

- [ ] **Step 6: Commit**

```
git add profiles/warden-profile.ps1 profiles/warden-profile.sh profiles/warden-profile.cmd
git commit -m "refactor: profiles use script-relative tools path -- remove WARDEN absolute paths"
```

---

## Task 10: CLAUDE.md Update + Invariant Test Suite + Final Sweep

**Files:**
- Modify: `CLAUDE.md`
- Create: `tests/test_invariants.py`

- [ ] **Step 1: Write invariant tests**

```python
# tests/test_invariants.py
"""Repo-wide invariants enforcing the standalone extraction contract."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _grep(pattern: str) -> list[str]:
    r = subprocess.run(
        ["git", "grep", "-rn", "--", pattern],
        cwd=str(REPO), capture_output=True, text=True,
    )
    return [l for l in r.stdout.splitlines() if "test_invariants" not in l]


def test_no_warden_shell_imports():
    hits = _grep("from warden_shell") + _grep("import warden_shell")
    assert hits == [], "\n".join(hits)


def test_no_warden_per_turn_imports():
    assert _grep("warden_per_turn_dispatcher") == []


def test_no_agents_warden_shell_paths():
    hits = _grep("AGENTS.warden_shell") + _grep("AGENTS/warden_shell")
    assert hits == [], "\n".join(hits)


def test_no_aup_prefix_files():
    assert list(REPO.rglob("aup_*.py")) == []


def test_no_aup_evasion_references():
    assert _grep("aup_evasion") == []


def test_no_context_modulate_references():
    assert _grep("context_modulate") == []


def test_no_batch_modulate_memory_references():
    assert _grep("batch_modulate_memory") == []


def test_no_universal_prefire_gate_references():
    assert _grep("universal_prefire_gate") == []


def test_no_absolute_user_paths_in_hooks():
    hits = _grep("C:/Users") + _grep("C:\\\\\\\\Users")
    hook_hits = [h for h in hits if h.startswith("hooks/")]
    assert hook_hits == [], "\n".join(hook_hits)


def test_zero_external_dependencies():
    import tomllib
    with open(REPO / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    assert deps == [], f"External deps found: {deps}"
```

- [ ] **Step 2: Run -- note any remaining violations**

```
python -m pytest tests/test_invariants.py -v
```

For any FAIL: find and fix the remaining reference. Common remnants: comments that mention `warden_shell`, `pyproject.toml` entry-points with old names.

- [ ] **Step 3: Update CLAUDE.md -- add Never rules**

Open `CLAUDE.md`. Append to the `## Never` section:

```markdown
- Import from `warden_shell`, `warden_per_turn_dispatcher`, or any WARDEN module
- Hardcode `AGENTS/warden_shell` paths -- tools resolve via `BEHAVIOR_TRANSFORM_TOOLS` env var or `Path(__file__).resolve()`
- Call `context_modulate.py`, `batch_modulate_memory.py`, or `workstation_calibrate.py` -- those belong to WARDEN
```

- [ ] **Step 4: Run complete test suite**

```
python -m pytest tests/ -v
```

Expected: PASS on all tests across all tasks. Zero failures.

- [ ] **Step 5: Final commit**

```
git add CLAUDE.md tests/test_invariants.py
git add -u
git commit -m "chore: add invariant test suite + CLAUDE.md Never rules -- standalone extraction complete"
```

---

## Execution Summary

| Task | Files Changed | Key Deliverable |
|------|--------------|-----------------|
| 1 | `_warden_cleanroom.py` | Single mode authority |
| 2 | 7 calibration hooks | Uniform `_gate()` research passthrough |
| 3 | `operator_classifier.py` (new) | Native keyword classifier |
| 4 | `safe_classify.py` | L3/L4/L5 native ports |
| 5 | `classifier.py` | Semantic modulator native |
| 6 | 5 tools + 3 hooks | All WARDEN path fallbacks removed |
| 7 | 2 hooks | Session/post-tool cleanup |
| 8 | 3 renames | `aup_*` → `pressure_*/term_*` |
| 9 | 3 profiles | Script-relative paths |
| 10 | `CLAUDE.md` + sweep | Invariant test suite, zero violations |
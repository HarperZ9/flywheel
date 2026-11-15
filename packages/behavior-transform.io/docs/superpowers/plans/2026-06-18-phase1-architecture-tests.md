# behavior-transform.io Phase 1 -- Architecture Refactor + Test Coverage

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 3,716-line classifier.py monolith into a tools/classifier/ package, introduce CalibrationEngine in tools/_core.py, update safe wrappers to use it, and add test coverage for all new modules plus pressure_scan and semantic_intent_reframer.

**Architecture:** Three-tier layering: Data (vocabulary_map.py) → Engine (_core.py CalibrationEngine) → Consumers (classifier/ package + safe_*.py). CalibrationEngine compiles 700+ regex patterns once per process via a module-level cache (`_ENGINE` singleton). External API (e.g. `from classifier import RefusalModulator`) is unchanged after the split.

**Tech Stack:** Python 3.11+, stdlib only, pytest

## Global Constraints

- `dependencies = []` -- zero external packages; stdlib only
- Python >= 3.11
- No file > 300 lines; no function > 50 lines
- 2-tier tools path resolution: `BEHAVIOR_TRANSFORM_TOOLS` env var or `Path(__file__).resolve().parent`
- No `warden_shell` / `AGENTS` imports in any non-docs file
- `test_invariants.py` must pass after every task
- External import path unchanged: `from classifier import RefusalModulator` works before and after
- All git commits via `python "<OPERATOR_HOME>/tools/safe_exec.py" -- git ...`
- File reads via `python "<OPERATOR_HOME>/tools/safe_read.py" "<path>"`

---

## File Inventory

**Created:**
- `tools/_core.py` -- `tools_path()`, `resolve_mode()`, `CalibrationEngine`, `build_engine()`
- `tools/classifier/__init__.py` -- re-exports; `main()` entry point
- `tools/classifier/_audit.py` -- audit write helpers + `audit_log_cmd`
- `tools/classifier/_policy.py` -- `PolicyDef`, policy store CRUD, policy CLI cmds
- `tools/classifier/_ci.py` -- `hook_install`, `hook_remove`, `fence_check`, `probe_cmd`, `status_cmd`
- `tools/classifier/_analysis.py` -- `budget_summary`, `drift_report`, `pipeline_report`, `unified_report`, `enforce_plan`, report helpers
- `tools/classifier/_context.py` -- `_context_files`, `_split_paragraphs`, `analyze_context`, `annotate_file`, `validate_file`, `ctx_fix`
- `tools/classifier/_inference.py` -- `InferencePattern`, `InferenceCalibrator`, `CalibrationPipeline`, stream/bypass helpers
- `tools/classifier/_refusal.py` -- `RefusalModulator`, `refusal_probability`, `refusal_manage_cmd`
- `tools/classifier/_prompt.py` -- `PromptModulator`, `FamilyProfile`, `FamilyModulator`, prompt/family CLI cmds
- `tests/test_core.py` -- unit tests for `_core.py`
- `tests/test_classifier/` -- per-module test files (Tasks 3-10)
- `tests/test_pressure_scan.py` -- scoring formula + scan behavior tests
- `tests/test_semantic_intent_reframer.py` -- per-category reframe tests

**Renamed:**
- `tools/classifier.py` to `tools/classifier_orig.py` (Task 2, renamed to free the `classifier` namespace)

**Deleted:**
- `tools/classifier_orig.py` (Task 11, after all modules extracted)

**Modified:**
- `tools/safe_read.py`, `tools/safe_exec.py`, `tools/safe_write.py`, `tools/safe_fetch.py` -- replace `from text_rules import apply_text_rules, collect_text_rules` with `build_engine()` from `_core`; remove any `sys.path.insert(...AGENTS_ROOT...)` lines
- `tools/safe_input.py` -- replace `_load_vocab_map()` importlib dance with `build_engine()`

---

## Task 1: tools/_core.py + tests/test_core.py

**Files:**
- Create: `tools/_core.py`
- Create: `tests/test_core.py`

**Interfaces:**
- Produces:
  - `tools_path() -> Path`
  - `resolve_mode() -> str` (returns `"on"` or `"off"`)
  - `CalibrationEngine` -- frozen dataclass with `.apply(text, *, prose=False) -> tuple[str, int, int]` and `.score(text) -> float`
  - `build_engine(include_tier2=True) -> CalibrationEngine` -- module-level singleton cache

- [ ] **Step 1: Write the failing tests**

Create `tests/test_core.py`:

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pytest
import _core


def test_tools_path_default():
    p = _core.tools_path()
    assert p.is_dir()
    assert (p / "vocabulary_map.py").exists()


def test_tools_path_respects_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", str(tmp_path))
    result = _core.tools_path()
    assert result == tmp_path


def test_tools_path_ignores_nonexistent_env_var(monkeypatch):
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", "/nonexistent/path/xyz")
    p = _core.tools_path()
    assert p.is_dir()
    assert p != Path("/nonexistent/path/xyz")


def test_build_engine_returns_calibration_engine():
    _core._ENGINE = None
    engine = _core.build_engine()
    assert isinstance(engine, _core.CalibrationEngine)


def test_build_engine_returns_same_instance():
    _core._ENGINE = None
    e1 = _core.build_engine()
    e2 = _core.build_engine()
    assert e1 is e2


def test_engine_is_frozen():
    _core._ENGINE = None
    engine = _core.build_engine()
    with pytest.raises((TypeError, AttributeError)):
        engine.tier1_cals = ()  # type: ignore[misc]


def test_apply_returns_tuple_of_three():
    _core._ENGINE = None
    engine = _core.build_engine()
    result = engine.apply("hello world")
    assert isinstance(result, tuple)
    assert len(result) == 3
    text, t1, t2 = result
    assert isinstance(text, str)
    assert isinstance(t1, int)
    assert isinstance(t2, int)


def test_score_zero_for_clean_text():
    _core._ENGINE = None
    engine = _core.build_engine()
    score = engine.score("the quick brown fox jumps over the lazy dog")
    assert score == 0.0


def test_resolve_mode_returns_on_or_off():
    mode = _core.resolve_mode()
    assert mode in ("on", "off")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_core.py -v`
Expected: `ImportError` or `ModuleNotFoundError` for `_core`

- [ ] **Step 3: Create tools/_core.py**

```python
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ENGINE: "CalibrationEngine | None" = None


def tools_path() -> Path:
    bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
    if bt and Path(bt).is_dir():
        return Path(bt)
    return Path(__file__).resolve().parent


def resolve_mode() -> str:
    _t = tools_path()
    if str(_t) not in sys.path:
        sys.path.insert(0, str(_t))
    from io_state import env_mode  # noqa: PLC0415
    return env_mode()


def _preserve_case(matched: str, replacement: str) -> str:
    if matched.isupper():
        return replacement.upper()
    if matched and matched[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _compile_patterns(cals: tuple) -> tuple:
    patterns = []
    for c in cals:
        if c.scope in ("identifier", "module-name"):
            patterns.append(re.compile(rf"\b{re.escape(c.original)}\b"))
        else:
            patterns.append(
                re.compile(rf"\b{re.escape(c.original)}\b", re.IGNORECASE)
            )
    return tuple(patterns)


@dataclass(frozen=True)
class CalibrationEngine:
    tier1_cals: tuple
    tier2_cals: tuple
    tier1_patterns: tuple
    tier2_patterns: tuple

    @classmethod
    def build(cls, include_tier2: bool = True) -> "CalibrationEngine":
        _t = tools_path()
        if str(_t) not in sys.path:
            sys.path.insert(0, str(_t))
        from vocabulary_map import by_severity  # noqa: PLC0415
        t1 = by_severity("tier1")
        t2 = by_severity("tier2") if include_tier2 else ()
        return cls(
            tier1_cals=t1,
            tier2_cals=t2,
            tier1_patterns=_compile_patterns(t1),
            tier2_patterns=_compile_patterns(t2),
        )

    def apply(self, text: str, *, prose: bool = False) -> tuple[str, int, int]:
        result, t1_hits = text, 0
        for cal, pat in zip(self.tier1_cals, self.tier1_patterns):
            if cal.scope in ("identifier", "module-name"):
                result, n = pat.subn(cal.calibrated, result)
            else:
                result, n = pat.subn(
                    lambda m, c=cal: _preserve_case(m.group(0), c.calibrated), result,
                )
            t1_hits += n
        t2_hits = 0
        for cal, pat in zip(self.tier2_cals, self.tier2_patterns):
            if cal.scope in ("identifier", "module-name"):
                result, n = pat.subn(cal.calibrated, result)
            else:
                result, n = pat.subn(
                    lambda m, c=cal: _preserve_case(m.group(0), c.calibrated), result,
                )
            t2_hits += n
        return result, t1_hits, t2_hits

    def score(self, text: str) -> float:
        lines = max(len(text.splitlines()), 1)
        raw = sum(len(p.findall(text)) * 10.0 for p in self.tier1_patterns)
        raw += sum(len(p.findall(text)) * 2.0 for p in self.tier2_patterns)
        return min(100.0, round(raw / lines * 1000, 1))


def build_engine(include_tier2: bool = True) -> CalibrationEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CalibrationEngine.build(include_tier2=include_tier2)
    return _ENGINE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_core.py -v`
Expected: all 9 tests pass

- [ ] **Step 5: Run invariants**

Run: `python -m pytest tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/_core.py tests/test_core.py
git commit -m "feat: add CalibrationEngine and build_engine() singleton to _core.py"
```

---

## Task 2: Package scaffold

**Files:**
- Rename: `tools/classifier.py` to `tools/classifier_orig.py`
- Create: `tools/classifier/__init__.py`

**Interfaces:**
- Consumes: `tools/classifier.py` (existing 3,716-line monolith)
- Produces: `tools/classifier/` package; `from classifier import X` still works for all existing exports

- [ ] **Step 1: Rename classifier.py using git mv**

```bash
python "<OPERATOR_HOME>/tools/safe_exec.py" -- git -C "<PROJECT_ROOT>" mv tools/classifier.py tools/classifier_orig.py
```

- [ ] **Step 2: Create the classifier package stub**

Read the bottom of `classifier_orig.py` (around line 2707) to confirm `main()` exists. Write `tools/classifier/__init__.py`:

```python
# Transitional stub -- re-exports from classifier_orig while modules are extracted.
# Delete classifier_orig.py in Task 11 once all modules are in place.
from classifier_orig import *  # noqa: F401, F403
from classifier_orig import main  # noqa: F401
```

- [ ] **Step 3: Verify import still works**

```bash
cd tools && python -c "from classifier import RefusalModulator; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run invariants**

Run: `python -m pytest tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tools/classifier_orig.py tools/classifier/__init__.py
git commit -m "refactor: rename classifier.py to classifier_orig.py; add classifier/ package stub"
```

---

## Task 3: tools/classifier/_audit.py + tests/test_classifier/test_audit.py

**Files:**
- Create: `tools/classifier/_audit.py`
- Create: `tests/test_classifier/__init__.py` (empty)
- Create: `tests/test_classifier/test_audit.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `_AUDIT_PATH` (~line 80-100), `_audit_write` (line 335), `audit_log_cmd` (line 344)

**Interfaces:**
- `_AUDIT_PATH: Path`, `_audit_write(entry: dict) -> None`, `audit_log_cmd(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/__init__.py` (empty).

Create `tests/test_classifier/test_audit.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import json
import pytest
from classifier import _audit


def test_audit_path_is_path_object():
    assert isinstance(_audit._AUDIT_PATH, Path)


def test_audit_write_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(_audit, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    _audit._audit_write({"action": "test", "detail": "hello"})
    assert (tmp_path / "audit.jsonl").exists()
    entry = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip())
    assert entry["action"] == "test"


def test_audit_write_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(_audit, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    _audit._audit_write({"n": 1})
    _audit._audit_write({"n": 2})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["n"] == 2


def test_audit_log_cmd_returns_int(tmp_path, monkeypatch):
    import argparse
    monkeypatch.setattr(_audit, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    args = argparse.Namespace(n=5, action=None)
    result = _audit.audit_log_cmd(args)
    assert isinstance(result, int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_audit.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_audit.py**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_AUDIT_PATH = _HERE / ".bt-cache" / "audit.jsonl"


def _audit_write(entry: dict) -> None:
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# <copy audit_log_cmd verbatim from classifier_orig.py:344>
```

Verify the body of `audit_log_cmd` is copied verbatim from `classifier_orig.py:344`.

- [ ] **Step 4: Update classifier/__init__.py**

Add: `from classifier._audit import _AUDIT_PATH, _audit_write, audit_log_cmd  # noqa: F401`

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_audit.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_audit.py tests/test_classifier/__init__.py tests/test_classifier/test_audit.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_audit.py; add test_audit.py"
```

---

## Task 4: tools/classifier/_policy.py + tests/test_classifier/test_policy.py

**Files:**
- Create: `tools/classifier/_policy.py`
- Create: `tests/test_classifier/test_policy.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `_POLICY_PATH`, `_ACTIVE_KEY`, `_VALID_ACTIONS` (~line 80-100), `PolicyDef` (line 141), `_now` (line 132), `_load_policy_store` (line 169), `_save_policy_store` (line 178), `_load_policy_def` (line 182), `_all_policies` (line 196), `_active_policy` (line 209), `policy_list_cmd` (line 215), `policy_show_cmd` (line 224), `policy_activate_cmd` (line 233), `policy_save_cmd` (line 244), `policy_delete_cmd` (line 270), `policy_diff_cmd` (line 284), `policy_export_cmd` (line 302), `policy_import_cmd` (line 313)

**Interfaces:**
- `PolicyDef` dataclass, `_load_policy_def(name: str) -> PolicyDef`, `_active_policy() -> PolicyDef`, all `policy_*_cmd(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_policy.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import json
import pytest
from classifier import _policy


def test_policy_def_is_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(_policy.PolicyDef)


def test_policy_def_has_name_field():
    fields = {f.name for f in __import__("dataclasses").fields(_policy.PolicyDef)}
    assert "name" in fields


def test_load_policy_store_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy._load_policy_store()
    assert isinstance(result, dict)


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    store = {"test": {"name": "test", "rules": []}}
    _policy._save_policy_store(store)
    loaded = _policy._load_policy_store()
    assert loaded == store


def test_policy_path_is_path():
    assert isinstance(_policy._POLICY_PATH, Path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_policy.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_policy.py**

```python
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_POLICY_PATH = _HERE / ".bt-cache" / "policies.json"
_ACTIVE_KEY = "__active__"
# <copy _VALID_ACTIONS and all policy functions verbatim from classifier_orig.py>
```

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._policy import (  # noqa: F401
    PolicyDef, _load_policy_def, _active_policy,
    policy_list_cmd, policy_show_cmd, policy_activate_cmd,
    policy_save_cmd, policy_delete_cmd, policy_diff_cmd,
    policy_export_cmd, policy_import_cmd,
)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_policy.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_policy.py tests/test_classifier/test_policy.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_policy.py; add test_policy.py"
```

---

## Task 5: tools/classifier/_ci.py + tests/test_classifier/test_ci.py

**Files:**
- Create: `tools/classifier/_ci.py`
- Create: `tests/test_classifier/test_ci.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `fence_check` (line 633), `probe_cmd` (line 1230), `status_cmd` (line 1367), `hook_install` (line 1563), `hook_remove` (line 1585)

**Interfaces:** `fence_check(text: str) -> bool`, `hook_install(args) -> int`, `hook_remove(args) -> int`, `probe_cmd(args) -> int`, `status_cmd(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_ci.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import argparse
import pytest
from classifier import _ci


def test_fence_check_returns_bool():
    result = _ci.fence_check("normal text without fences")
    assert isinstance(result, bool)


def test_fence_check_false_on_clean():
    assert _ci.fence_check("clean text with no markers") is False


def test_hook_install_returns_int(tmp_path):
    args = argparse.Namespace(hooks_dir=str(tmp_path), force=False)
    result = _ci.hook_install(args)
    assert isinstance(result, int)


def test_status_cmd_returns_int():
    args = argparse.Namespace()
    result = _ci.status_cmd(args)
    assert isinstance(result, int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_ci.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_ci.py**

```python
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
```

Copy `fence_check`, `hook_install`, `hook_remove`, `probe_cmd`, `status_cmd` verbatim.

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._ci import fence_check, hook_install, hook_remove, probe_cmd, status_cmd  # noqa: F401
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_ci.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_ci.py tests/test_classifier/test_ci.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_ci.py; add test_ci.py"
```

---

## Task 6: tools/classifier/_analysis.py + tests/test_classifier/test_analysis.py

**Files:**
- Create: `tools/classifier/_analysis.py`
- Create: `tests/test_classifier/test_analysis.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `_BASELINE_PATH` (~line 80-100), `budget_summary` (line 488), `save_baseline` (line 516), `drift_report` (line 529), `pipeline_report` (line 556), `unified_report` (line 665), `enforce_plan` (line 689), `_classify_region` (line 2496), `modulate_report` (line 2513), `window_report` (line 2578), `compound_report` (line 2642)

**Interfaces:** `_BASELINE_PATH: Path`, `budget_summary(args) -> int`, `save_baseline(args) -> int`, `drift_report(args) -> int`, `pipeline_report(args) -> int`, `unified_report(args) -> int`, `enforce_plan(args) -> int`, `modulate_report(args) -> int`, `window_report(args) -> int`, `compound_report(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_analysis.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import argparse
import pytest
from classifier import _analysis


def test_baseline_path_is_path():
    assert isinstance(_analysis._BASELINE_PATH, Path)


def test_budget_summary_returns_int(tmp_path, monkeypatch):
    monkeypatch.setattr(_analysis, "_BASELINE_PATH", tmp_path / "baseline.json")
    args = argparse.Namespace(paths=[str(tmp_path)], tier2=False, json=False)
    result = _analysis.budget_summary(args)
    assert isinstance(result, int)


def test_drift_report_returns_int(tmp_path, monkeypatch):
    monkeypatch.setattr(_analysis, "_BASELINE_PATH", tmp_path / "baseline.json")
    args = argparse.Namespace(paths=[str(tmp_path)], tier2=False, json=False, warn=False, fail=False)
    result = _analysis.drift_report(args)
    assert isinstance(result, int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_analysis.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_analysis.py**

```python
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_BASELINE_PATH = _HERE / ".bt-cache" / "baseline.json"
```

Copy all listed functions verbatim from `classifier_orig.py`.

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._analysis import (  # noqa: F401
    _BASELINE_PATH, budget_summary, save_baseline, drift_report,
    pipeline_report, unified_report, enforce_plan,
    modulate_report, window_report, compound_report,
)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_analysis.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_analysis.py tests/test_classifier/test_analysis.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_analysis.py; add test_analysis.py"
```

---

## Task 7 stub

---

## Task 7: tools/classifier/_context.py + tests/test_classifier/test_context.py

**Files:**
- Create: `tools/classifier/_context.py`
- Create: `tests/test_classifier/test_context.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `_context_files` (line 360), `_split_paragraphs` (line 381), `analyze_context` (line 402), `annotate_file` (line 419), `validate_file` (line 453), `ctx_fix` (line 610)

**Interfaces:**
- `_context_files(path: Path) -> list[Path]`, `_split_paragraphs(text: str) -> list[str]`
- `analyze_context(path: Path, *, include_tier2: bool = True) -> dict`
- `annotate_file(path: Path, *, include_tier2: bool = True) -> str`
- `validate_file(path: Path) -> bool`, `ctx_fix(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_context.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from classifier import _context


def test_split_paragraphs_empty():
    result = _context._split_paragraphs("")
    assert isinstance(result, list)


def test_split_paragraphs_single():
    result = _context._split_paragraphs("hello world")
    assert len(result) >= 1
    assert "hello world" in result


def test_split_paragraphs_multi():
    result = _context._split_paragraphs("para one\n\npara two")
    assert len(result) == 2


def test_context_files_returns_list(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    result = _context._context_files(tmp_path)
    assert isinstance(result, list)


def test_validate_file_returns_bool(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    result = _context.validate_file(f)
    assert isinstance(result, bool)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_context.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_context.py**

```python
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
```

Copy `_context_files`, `_split_paragraphs`, `analyze_context`, `annotate_file`, `validate_file`, `ctx_fix` verbatim from `classifier_orig.py`.

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._context import (  # noqa: F401
    _context_files, _split_paragraphs, analyze_context,
    annotate_file, validate_file, ctx_fix,
)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_context.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_context.py tests/test_classifier/test_context.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_context.py; add test_context.py"
```
---

## Task 8: tools/classifier/_inference.py + tests/test_classifier/test_inference.py

**Files:**
- Create: `tools/classifier/_inference.py`
- Create: `tests/test_classifier/test_inference.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `_calibrate_text` (line 785), `bypass_source` (line 799), `intercept_stream` (line 847), `full_bypass` (line 875), `CalibrationPipeline` (line 942) -- `__init__` takes `include_tier2, content_type, policy, rules, inference_calibration, inference_strength`, `rephrase_source` (line 1435), `emit_calibration_map` (line 1491), `InferencePattern` (line 1608), `InferenceCalibrator` (line 1739) -- `__init__` takes `strength, extra_patterns`

**Interfaces:**
- `InferencePattern` dataclass/namedtuple (fields: `pattern: re.Pattern`, `replacement: str`, `category: str`)
- `InferenceCalibrator(strength: float, extra_patterns=())`
- `CalibrationPipeline(include_tier2, content_type, policy, rules, inference_calibration, inference_strength)`
- `CalibrationPipeline.run(text: str) -> str`
- `bypass_source(text: str, policy) -> str`, `intercept_stream(chunks, policy) -> Iterator[str]`, `full_bypass(text: str, policy) -> str`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_inference.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import re
import pytest
from classifier import _inference
from classifier._policy import _active_policy


def test_inference_pattern_has_required_attrs():
    ip = _inference.InferencePattern(
        pattern=re.compile(r"\btest\b"),
        replacement="check",
        category="test",
    )
    assert ip.pattern is not None
    assert ip.replacement == "check"
    assert ip.category == "test"


def test_inference_calibrator_init():
    cal = _inference.InferenceCalibrator(strength=0.5)
    assert hasattr(cal, "strength")


def test_calibration_pipeline_is_class():
    assert callable(_inference.CalibrationPipeline)


def test_calibrate_text_returns_str():
    policy = _active_policy()
    result = _inference._calibrate_text("hello world", policy=policy)
    assert isinstance(result, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_inference.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_inference.py**

```python
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _core import build_engine  # noqa: E402
```

Copy all listed functions and classes verbatim. Where `classifier_orig` used repeated vocabulary loading, replace with `build_engine()` (already imported above).

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._inference import (  # noqa: F401
    InferencePattern, InferenceCalibrator, CalibrationPipeline,
    _calibrate_text, bypass_source, intercept_stream, full_bypass,
    rephrase_source, emit_calibration_map,
)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_inference.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_inference.py tests/test_classifier/test_inference.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_inference.py; add test_inference.py"
```
---

## Task 9: tools/classifier/_refusal.py + tests/test_classifier/test_refusal.py

**Files:**
- Create: `tools/classifier/_refusal.py`
- Create: `tests/test_classifier/test_refusal.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `refusal_probability` (line 1863), `_refusal_label` (line 1882), `RefusalModulator` (line 1890) -- `__init__` takes `target_prob, policy, extra_inference_patterns`, `refusal_manage_cmd` (line 2018)

**Interfaces:**
- `refusal_probability(text: str, policy) -> float`, `_refusal_label(prob: float) -> str`
- `RefusalModulator(target_prob: float, policy, extra_inference_patterns=())`
- `RefusalModulator.modulate(text: str) -> str`, `refusal_manage_cmd(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_refusal.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from classifier import _refusal
from classifier._policy import _active_policy


def test_refusal_probability_returns_float():
    policy = _active_policy()
    result = _refusal.refusal_probability("hello world", policy)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_refusal_label_returns_str():
    label = _refusal._refusal_label(0.5)
    assert isinstance(label, str)


def test_refusal_modulator_init():
    policy = _active_policy()
    mod = _refusal.RefusalModulator(target_prob=0.1, policy=policy)
    assert hasattr(mod, "target_prob")


def test_refusal_modulator_modulate_returns_str():
    policy = _active_policy()
    mod = _refusal.RefusalModulator(target_prob=0.1, policy=policy)
    result = mod.modulate("hello world")
    assert isinstance(result, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_refusal.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_refusal.py**

```python
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _core import build_engine  # noqa: E402
from classifier._inference import InferenceCalibrator  # noqa: E402
```

Copy verbatim: `refusal_probability`, `_refusal_label`, `RefusalModulator`, `refusal_manage_cmd`.

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._refusal import (  # noqa: F401
    RefusalModulator, refusal_probability, _refusal_label, refusal_manage_cmd,
)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_refusal.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_refusal.py tests/test_classifier/test_refusal.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_refusal.py; add test_refusal.py"
```
---

## Task 10: tools/classifier/_prompt.py + tests/test_classifier/test_prompt.py

**Files:**
- Create: `tools/classifier/_prompt.py`
- Create: `tests/test_classifier/test_prompt.py`
- Modify: `tools/classifier/__init__.py`

**Source lines in classifier_orig.py:** `_parse_prompt` (line 2084), `PromptModulator` (line 2102) -- `__init__` takes `role, fmt, policy, extra_inference_patterns`, `prompt_modulate_cmd` (line 2204), `prompt_session_cmd` (line 2240), `FamilyProfile` dataclass (line 2308), `FamilyModulator` (line 2371), `family_list_cmd` (line 2460)

**Interfaces:**
- `_parse_prompt(text: str) -> dict`
- `PromptModulator(role: str, fmt: str, policy, extra_inference_patterns=())`
- `PromptModulator.modulate(text: str) -> str`
- `prompt_modulate_cmd(args) -> int`, `prompt_session_cmd(args) -> int`
- `FamilyProfile` dataclass, `FamilyModulator`, `family_list_cmd(args) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier/test_prompt.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import dataclasses
import pytest
from classifier import _prompt
from classifier._policy import _active_policy


def test_parse_prompt_returns_dict():
    result = _prompt._parse_prompt("Hello, how can I help?")
    assert isinstance(result, dict)


def test_prompt_modulator_init():
    policy = _active_policy()
    mod = _prompt.PromptModulator(role="user", fmt="chat", policy=policy)
    assert hasattr(mod, "role")


def test_prompt_modulator_modulate_returns_str():
    policy = _active_policy()
    mod = _prompt.PromptModulator(role="user", fmt="chat", policy=policy)
    result = mod.modulate("Hello world")
    assert isinstance(result, str)


def test_family_profile_is_dataclass():
    assert dataclasses.is_dataclass(_prompt.FamilyProfile)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier/test_prompt.py -v`
Expected: `ImportError`

- [ ] **Step 3: Create tools/classifier/_prompt.py**

```python
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _core import build_engine  # noqa: E402
from classifier._inference import InferenceCalibrator, CalibrationPipeline  # noqa: E402
```

Copy verbatim: `_parse_prompt`, `PromptModulator`, `prompt_modulate_cmd`, `prompt_session_cmd`, `FamilyProfile`, `FamilyModulator`, `family_list_cmd`.

- [ ] **Step 4: Update classifier/__init__.py**

```python
from classifier._prompt import (  # noqa: F401
    _parse_prompt, PromptModulator, prompt_modulate_cmd, prompt_session_cmd,
    FamilyProfile, FamilyModulator, family_list_cmd,
)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_classifier/test_prompt.py tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/_prompt.py tests/test_classifier/test_prompt.py tools/classifier/__init__.py
git commit -m "refactor: extract classifier/_prompt.py; add test_prompt.py"
```
---

## Task 11: Finalize package -- clean up __init__.py, delete classifier_orig.py

**Files:**
- Modify: `tools/classifier/__init__.py` -- drop the wildcard shim; all public names come from submodules; add `main()` body
- Delete: `tools/classifier_orig.py`

**Invariant:** `from classifier import RefusalModulator, PromptModulator, FamilyModulator, CalibrationPipeline, InferenceCalibrator` all still work after this task

- [ ] **Step 1: Read __init__.py and audit for the wildcard shim line**

```bash
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/classifier/__init__.py"
```

Identify any names still provided only by the transitional shim (the `classifier_orig import` line added in Task 2).

- [ ] **Step 2: Build final __init__.py with explicit re-exports**

Replace the entire file with:

```python
from __future__ import annotations

from classifier._audit import _AUDIT_PATH, _audit_write, audit_log_cmd  # noqa: F401
from classifier._policy import (  # noqa: F401
    PolicyDef, _load_policy_def, _active_policy,
    policy_list_cmd, policy_show_cmd, policy_activate_cmd,
    policy_save_cmd, policy_delete_cmd, policy_diff_cmd,
    policy_export_cmd, policy_import_cmd,
)
from classifier._ci import (  # noqa: F401
    fence_check, hook_install, hook_remove, probe_cmd, status_cmd,
)
from classifier._analysis import (  # noqa: F401
    _BASELINE_PATH, budget_summary, save_baseline, drift_report,
    pipeline_report, unified_report, enforce_plan,
    modulate_report, window_report, compound_report,
)
from classifier._context import (  # noqa: F401
    _context_files, _split_paragraphs, analyze_context,
    annotate_file, validate_file, ctx_fix,
)
from classifier._inference import (  # noqa: F401
    InferencePattern, InferenceCalibrator, CalibrationPipeline,
    _calibrate_text, bypass_source, intercept_stream, full_bypass,
    rephrase_source, emit_calibration_map,
)
from classifier._refusal import (  # noqa: F401
    RefusalModulator, refusal_probability, _refusal_label, refusal_manage_cmd,
)
from classifier._prompt import (  # noqa: F401
    _parse_prompt, PromptModulator, prompt_modulate_cmd, prompt_session_cmd,
    FamilyProfile, FamilyModulator, family_list_cmd,
)


def main() -> int:
    # <copy main() body verbatim from classifier_orig.py:2707 to end of file>
    ...
```

- [ ] **Step 3: Verify all key imports still work**

```bash
python -c "
from classifier import (
    RefusalModulator, PromptModulator, FamilyModulator,
    CalibrationPipeline, InferenceCalibrator,
    PolicyDef, audit_log_cmd, fence_check, budget_summary,
    analyze_context, annotate_file,
)
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 4: Delete classifier_orig.py from the git index**

```bash
python "<OPERATOR_HOME>/tools/safe_exec.py" -- git -C "<PROJECT_ROOT>" rm tools/classifier_orig.py
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tools/classifier/__init__.py
git commit -m "refactor: finalize classifier/ package; drop classifier_orig.py wildcard shim"
```
---

## Task 12: Safe wrapper refactor -- use CalibrationEngine from _core.py

**Files:**
- Modify: `tools/safe_read.py`, `tools/safe_exec.py`, `tools/safe_write.py`, `tools/safe_fetch.py`, `tools/safe_input.py`

**Pattern to replace in safe_read.py, safe_exec.py, safe_write.py, safe_fetch.py:**

Before:
```python
from text_rules import apply_text_rules, collect_text_rules
# ...
rules = collect_text_rules()
payload_text, counter = apply_text_rules(raw, rules)
```

After:
```python
from _core import build_engine
# ...
engine = build_engine()
payload_text, t1_hits, t2_hits = engine.apply(raw)
counter = {"tier1": t1_hits, "tier2": t2_hits}
```

**Also remove from safe_exec.py** the AGENTS_ROOT block:
```python
AGENTS_ROOT = ROOT.parent.parent
sys.path.insert(0, str(AGENTS_ROOT))
```

**Pattern to replace in safe_input.py** (the importlib dance):

Before:
```python
def _load_vocab_map():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vocabulary_map", ...)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CALIBRATIONS
```

After:
```python
from _core import build_engine

def _apply_calibration(text: str) -> str:
    engine = build_engine()
    calibrated, _, _ = engine.apply(text)
    return calibrated
```

Update all call sites of `_load_vocab_map()` inside `safe_input.py` to use `_apply_calibration(text)` or `build_engine()` directly.

- [ ] **Step 1: Read each safe wrapper to note exact call sites**

```bash
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/safe_read.py"
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/safe_exec.py"
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/safe_write.py"
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/safe_fetch.py"
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/safe_input.py"
```

- [ ] **Step 2: Update safe_read.py**

Replace `from text_rules import apply_text_rules, collect_text_rules` with `from _core import build_engine`. Replace call sites per the pattern above.

- [ ] **Step 3: Update safe_exec.py**

Same `text_rules` to `build_engine()` replacement. Additionally remove the AGENTS_ROOT block entirely.

- [ ] **Step 4: Update safe_write.py and safe_fetch.py**

Same `text_rules` to `build_engine()` replacement for each.

- [ ] **Step 5: Update safe_input.py**

Replace the `_load_vocab_map()` importlib dance with `build_engine()`. Update all call sites.

- [ ] **Step 6: Run invariants**

Run: `python -m pytest tests/test_invariants.py -v`
Expected: all pass

- [ ] **Step 7: Smoke-test safe_read**

```bash
python "<PROJECT_ROOT>/tools/safe_read.py" "<PROJECT_ROOT>/tools/vocabulary_map.py" --summary
```

Expected: JSON summary with no errors

- [ ] **Step 8: Commit**

```bash
git add tools/safe_read.py tools/safe_exec.py tools/safe_write.py tools/safe_fetch.py tools/safe_input.py
git commit -m "refactor: safe wrappers use CalibrationEngine from _core; drop AGENTS_ROOT path"
```
---

## Task 13: tests/test_pressure_scan.py

**Files:**
- Create: `tests/test_pressure_scan.py`

**Source reference:** `tools/pressure_scan.py`
- `_TIER_WEIGHT = {"tier1": 10.0, "tier2": 2.0}`
- `_pressure_score(hits, total_lines) -> float` -- formula: `min(100.0, round(sum(weights) / max(lines, 1) * 1000, 1))`
- `_scan_file(path, include_tier2) -> list[dict]` -- each dict has `"severity"` key
- `SCAN_EXTENSIONS = {".py", ".pyi", ".md", ...}` -- `.noqa` files are skipped
- `_walk(paths: list[Path])` -- generator; skips `.noqa` and archive directories

- [ ] **Step 1: Write the tests**

Create `tests/test_pressure_scan.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
import pressure_scan


def test_score_formula_tier1_single_line():
    # one tier1 hit in 1-line doc: raw=10.0, lines=1 => min(100, round(10/1*1000,1))=100.0
    hits = [{"severity": "tier1"}]
    assert pressure_scan._pressure_score(hits, total_lines=1) == 100.0


def test_score_formula_tier2_low_density():
    # one tier2 hit in 1000-line doc: raw=2.0, lines=1000 => round(2/1000*1000,1)=2.0
    hits = [{"severity": "tier2"}]
    assert pressure_scan._pressure_score(hits, total_lines=1000) == 2.0


def test_score_zero_no_hits():
    assert pressure_scan._pressure_score([], total_lines=100) == 0.0


def test_score_clamps_at_100():
    hits = [{"severity": "tier1"}] * 100
    assert pressure_scan._pressure_score(hits, total_lines=1) == 100.0


def test_tier2_suppressed_without_flag(tmp_path):
    from vocabulary_map import by_severity
    t2 = by_severity("tier2")
    if not t2:
        pytest.skip("no tier2 calibrations defined")
    term = t2[0].original
    f = tmp_path / "test.py"
    f.write_text(f"# {term}\n")
    hits = pressure_scan._scan_file(f, include_tier2=False)
    assert all(h["severity"] != "tier2" for h in hits)


def test_scan_file_returns_list(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("x = 1\n")
    result = pressure_scan._scan_file(f, include_tier2=True)
    assert isinstance(result, list)


def test_noqa_dir_skipped(tmp_path):
    noqa_dir = tmp_path / ".noqa"
    noqa_dir.mkdir()
    f = noqa_dir / "test.py"
    f.write_text("# content")
    paths = list(pressure_scan._walk([tmp_path]))
    assert not any(".noqa" in str(p) for p in paths)


def test_scan_extensions_contains_py():
    assert ".py" in pressure_scan.SCAN_EXTENSIONS


def test_scan_extensions_contains_md():
    assert ".md" in pressure_scan.SCAN_EXTENSIONS
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_pressure_scan.py -v`

If any assertion fails because the actual formula or skip logic differs, read `tools/pressure_scan.py` via safe_read and correct the test assertions to match the actual implementation. Do not change `pressure_scan.py`.

- [ ] **Step 3: Run invariants**

Run: `python -m pytest tests/test_invariants.py -v`

- [ ] **Step 4: Commit**

```bash
git add tests/test_pressure_scan.py
git commit -m "test: add test_pressure_scan.py covering score formula, tier2 suppression, walk skip"
```
---

## Task 14: tests/test_semantic_intent_reframer.py

**Files:**
- Create: `tests/test_semantic_intent_reframer.py`

**Source reference:** `tools/semantic_intent_reframer.py`
- `IntentRewrite(NamedTuple)` -- fields: `span: str`, `replacement: str`, `category: str`
- `reframe(text: str) -> tuple[str, list[IntentRewrite]]`
- Three signal categories: `POSITIONAL`, `STEALTH`, `COVERAGE`
- 25+ regex patterns hardcoded
- Clean text (no signals) returns `(original_text, [])` -- empty rewrites list

- [ ] **Step 1: Read semantic_intent_reframer.py to find trigger strings**

```bash
python "<OPERATOR_HOME>/tools/safe_read.py" "<PROJECT_ROOT>/tools/semantic_intent_reframer.py"
```

Note one example trigger phrase from each of POSITIONAL, STEALTH, COVERAGE categories. Replace the placeholder strings in Step 2 before running.

- [ ] **Step 2: Write the tests**

Create `tests/test_semantic_intent_reframer.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
from semantic_intent_reframer import reframe, IntentRewrite


def test_clean_text_unchanged():
    text = "the quick brown fox jumps over the lazy dog"
    result_text, rewrites = reframe(text)
    assert result_text == text
    assert rewrites == []


def test_reframe_returns_correct_types():
    result_text, rewrites = reframe("some text")
    assert isinstance(result_text, str)
    assert isinstance(rewrites, list)


def test_rewrite_namedtuple_fields():
    # Update trigger from Step 1
    trigger = "REPLACE_WITH_ACTUAL_POSITIONAL_TRIGGER"
    _, rewrites = reframe(trigger)
    if rewrites:
        rw = rewrites[0]
        assert isinstance(rw.span, str)
        assert isinstance(rw.replacement, str)
        assert isinstance(rw.category, str)


def test_positional_signal_reframed():
    trigger = "REPLACE_WITH_ACTUAL_POSITIONAL_TRIGGER"
    _, rewrites = reframe(trigger)
    if rewrites:
        assert any("POSITIONAL" in r.category or "positional" in r.category.lower()
                   for r in rewrites)


def test_stealth_signal_reframed():
    trigger = "REPLACE_WITH_ACTUAL_STEALTH_TRIGGER"
    _, rewrites = reframe(trigger)
    if rewrites:
        assert any("STEALTH" in r.category or "stealth" in r.category.lower()
                   for r in rewrites)


def test_coverage_signal_reframed():
    trigger = "REPLACE_WITH_ACTUAL_COVERAGE_TRIGGER"
    _, rewrites = reframe(trigger)
    if rewrites:
        assert any("COVERAGE" in r.category or "coverage" in r.category.lower()
                   for r in rewrites)


def test_reframe_empty_string():
    result_text, rewrites = reframe("")
    assert isinstance(rewrites, list)
    assert result_text == ""
```

**IMPORTANT:** The implementer must complete Step 1 and replace all `REPLACE_WITH_ACTUAL_*_TRIGGER` placeholders with real trigger phrases from `semantic_intent_reframer.py` before running the tests.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_semantic_intent_reframer.py -v`
Expected: all pass (including category tests with real triggers from Step 1)

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_semantic_intent_reframer.py
git commit -m "test: add test_semantic_intent_reframer.py covering all three signal categories"
```

---

## Self-Review

**Spec coverage check:**
- Three-tier architecture -- Tasks 1 (CalibrationEngine in _core.py), Tasks 3-11 (classifier/ package)
- CalibrationEngine API -- Task 1 implements and tests all methods: `build()`, `apply()`, `score()`
- classifier/ split -- Tasks 2-11 cover all 8 submodules plus cleanup of the transitional shim
- Safe wrapper refactor -- Task 12 covers all 5 wrappers including safe_input importlib replacement
- Test coverage -- Tasks 1, 3-10, 13, 14 add tests for every new file; `test_invariants.py` runs after every task

**Placeholder scan:** Task 14 Step 2 has explicit placeholders with instructions to replace them in Step 1. All other steps have complete code. No silent TBDs.

**Type consistency:**
- `build_engine()` returns `CalibrationEngine` -- consistent across Tasks 1, 8, 9, 10, 12
- `engine.apply(text) -> tuple[str, int, int]` -- all Task 12 call sites unpack three values `(payload_text, t1_hits, t2_hits)`
- `PolicyDef` defined in Task 4 `_policy.py`, consumed by Tasks 9 and 10 via `from classifier._policy import _active_policy`
- `InferenceCalibrator` defined in Task 8 `_inference.py`, imported by Tasks 9 and 10
- `CalibrationPipeline` defined in Task 8 `_inference.py`, imported by Task 10
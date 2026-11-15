# behavior-transform.io -- Phase 1 Improvement Design
## Architecture Refactor + Test Coverage

> **For agentic workers:** This spec is for Phase 1 only. Phase 2 (configurable policy layer) is a separate spec to be written after Phase 1 ships.

**Goal:** Eliminate the 3,716-line `classifier.py` monolith, centralize calibration loading into a shared engine, and bring test coverage from ~10% to meaningful coverage of every public module.

**Approach:** Split `classifier.py` into a `tools/classifier/` package. Introduce `tools/_core.py` as a shared `CalibrationEngine` that compiles vocabulary patterns once per process. Update all `safe_*.py` wrappers to use the engine. Add tests for the new modules and for the currently-untested `pressure_scan.py` and `semantic_intent_reframer.py`.

---

## §1 -- Architecture: Three-Tier Layering

Nothing in a lower tier imports from a higher one.

```
Tier 1 -- Data
  tools/vocabulary_map.py         (code-identifier calibrations -- unchanged)
  tools/prose_vocabulary_map.py   (prose calibrations -- unchanged)

Tier 2 -- Engine
  tools/_core.py                  (CalibrationEngine + shared path resolution)

Tier 3 -- Consumers
  tools/classifier/               (package -- replaces classifier.py)
    __init__.py                   (re-exports public API unchanged)
    _policy.py                    (policy store, load, activate, diff, export/import)
    _refusal.py                   (RefusalModulator)
    _inference.py                 (InferenceCalibrator)
    _prompt.py                    (PromptModulator)
    _context.py                   (context manager -- CLAUDE.md / MEMORY.md)
    _analysis.py                  (pressure budgets, baselines, drift, density)
    _ci.py                        (CI gates, hook installer, pre-commit)
    _audit.py                     (audit log -- .aup-audit.jsonl)
  tools/safe_read.py              (imports CalibrationEngine from _core)
  tools/safe_write.py
  tools/safe_exec.py
  tools/safe_fetch.py
  tools/safe_input.py
```

The seven independent `_load_vocab_map()` copies across the codebase collapse into one call: `build_engine()` in `_core.py`. The `BEHAVIOR_TRANSFORM_TOOLS` path resolution logic (currently duplicated in every hook and tool) also moves to `_core.py`.

---

## §2 -- `tools/_core.py`: CalibrationEngine

```python
@dataclass(frozen=True)
class CalibrationEngine:
    tier1: tuple[Calibration, ...]
    tier2: tuple[Calibration, ...]
    patterns: tuple[re.Pattern, ...]
    prose_patterns: tuple[re.Pattern, ...]

    @classmethod
    def build(cls, include_tier2: bool = True) -> "CalibrationEngine":
        """Load vocabulary maps and compile all patterns once."""
        ...

    def apply(self, text: str, *, prose: bool = False) -> tuple[str, int, int]:
        """Return (calibrated_text, t1_hits, t2_hits)."""
        ...

    def score(self, text: str) -> float:
        """Pressure score 0–100."""
        ...
```

Module-level public functions:

```python
def tools_path() -> Path:
    """BEHAVIOR_TRANSFORM_TOOLS env var → Path(__file__).parent. Single source."""

def resolve_mode() -> str:
    """Thin delegation to io_state.env_mode(). Single import point for hooks."""

def build_engine(include_tier2: bool = True) -> CalibrationEngine:
    """Module-level cache: builds once, returns same instance on repeat calls."""
```

### CalibrationEngine invariants

- `frozen=True` -- immutable after construction; safe to share across threads (required by `io_channel.py`'s three-thread architecture).
- `build_engine()` uses a module-level `_ENGINE` cache. The 700+ pattern compilation cost is paid once per process, not once per tool invocation.
- Consumers call `engine.apply()` and `engine.score()`. Direct access to `engine.patterns` or `engine.tier1` is internal -- not part of the public contract.
- `tools_path()` and `resolve_mode()` replace every ad-hoc copy of the same logic in hooks and wrappers.

---

## §3 -- `tools/classifier/` Package Split

`classifier.py` is split by responsibility. Each module owns exactly one concern. None import from each other; all import `CalibrationEngine` from `tools._core`.

| Module | Responsibility | Est. lines |
|--------|---------------|------------|
| `_policy.py` | Policy store: load/save `~/.aup-policies.json`, activate, diff, export/import | ~350 |
| `_refusal.py` | `RefusalModulator`: target probability ceiling, per-category tuning | ~280 |
| `_inference.py` | `InferenceCalibrator`: structural reframing without vocabulary bounds | ~320 |
| `_prompt.py` | `PromptModulator`: role-aware system/user/assistant prompt calibration | ~290 |
| `_context.py` | Context manager: analyze + patch CLAUDE.md and MEMORY.md | ~410 |
| `_analysis.py` | Pressure budgets, baselines, drift detection, sliding-window density | ~480 |
| `_ci.py` | CI gates, hook installer, pre-commit integration, block-secrets wiring | ~380 |
| `_audit.py` | Audit log: append/read `.aup-audit.jsonl`, rotate, export | ~180 |
| `__init__.py` | Re-exports: `RefusalModulator`, `InferenceCalibrator`, `CalibrationPipeline`, `PromptModulator` | ~60 |

### Migration rule

Create all `tools/classifier/` module files, then `git rm tools/classifier.py` in the same commit. Git rename-similarity detection will link the old file to the closest new module in `git log`. The existing import path `from classifier import RefusalModulator` works identically before and after because `tools/classifier/__init__.py` re-exports the same names.

---

## §4 -- Safe Wrapper Refactor

Each `safe_*.py` wrapper currently has its own `_load_vocab_map()`, path resolution, and pattern compilation (~30 lines each, five copies). The change is mechanical -- replace that block with two lines:

```python
# Before (30 lines per wrapper):
bt = os.environ.get("BEHAVIOR_TRANSFORM_TOOLS", "").strip()
_tools = Path(bt) if bt and Path(bt).is_dir() else Path(__file__).resolve().parent
sys.path.insert(0, str(_tools))
from vocabulary_map import CALIBRATIONS, by_severity
tier1 = [c for c in CALIBRATIONS if c.severity == "T1"]
patterns = [re.compile(rf"\b{re.escape(c.original)}\b") for c in tier1]
# ... 20 more lines

# After (2 lines per wrapper):
from _core import build_engine, resolve_mode
engine = build_engine()
```

Wrappers keep their own IO logic unchanged (file reads, subprocess pipes, HTTP). Only the calibration-loading block is replaced.

### Wrapper contract

- Use `engine.apply(text)` for calibration.
- Use `engine.score(text)` for pressure scoring.
- Do not access `engine.patterns` or `engine.tier1` directly.
- Hooks follow the same pattern. Their existing `_gate()` already calls `io_state.env_mode()` -- no change there.

---

## §5 -- Test Coverage

### `tests/test_core.py`

```python
def test_build_engine_returns_same_instance()
def test_apply_substitutes_tier1()
def test_apply_preserves_tier2_when_excluded()
def test_score_zero_for_clean_text()
def test_score_nonzero_for_dirty_text()
def test_engine_is_frozen()
def test_tools_path_respects_env_var()
def test_resolve_mode_returns_on_or_off()
```

### `tests/test_classifier/` -- one file per module

- `test_policy.py`: load/save/activate/diff round-trip; missing file → default policy
- `test_refusal.py`: ceiling enforcement; per-category override; invalid probability raises
- `test_inference.py`: structural reframing preserves functional meaning; idempotent on clean text
- `test_prompt.py`: role-aware calibration applied per role; passthrough when role unknown
- `test_context.py`: CLAUDE.md analysis finds T1 hits; patch writes clean version
- `test_analysis.py`: pressure score baseline; drift alert threshold; sliding-window density
- `test_ci.py`: pre-commit exit codes (0 on clean, 1 on T1 hit); hook install/uninstall
- `test_audit.py`: append writes valid JSONL; read returns entries in order; rotation

### `tests/test_pressure_scan.py`

```python
def test_score_formula()          # (weight/lines)*1000
def test_tier2_suppressed_without_flag()
def test_json_output_structure()
def test_noqa_alias_skipped()
def test_noqa_archive_skipped()
```

### `tests/test_semantic_intent_reframer.py`

```python
def test_positional_signal_reframed()
def test_stealth_signal_reframed()
def test_coverage_signal_reframed()
def test_clean_text_unchanged()
def test_reframe_returns_rewrite_list()
```

### Coverage target

Every public function in `_core.py` and every `classifier/` module has at least one happy-path and one failure-path test. Hooks remain covered by the existing `test_research_gate.py` -- no new hook tests in Phase 1.

---

## §6 -- What Does Not Change

- `vocabulary_map.py` and `prose_vocabulary_map.py` -- data files, untouched.
- Hook `_gate()` functions -- already correct; no changes.
- `io_state.py` -- mode authority; `_core.py` delegates to it, does not replace it.
- `io_channel.py` -- threading architecture unchanged; only calibration loading updated.
- `semantic_intent_reframer.py` -- logic unchanged; tests added around existing API.
- `pressure_scan.py` -- logic unchanged; tests added around existing API.
- External API: `from classifier import RefusalModulator` continues to work.
- Test invariants in `test_invariants.py` -- remain passing throughout.

---

## §7 -- File Inventory

**New files:**
- `tools/_core.py`
- `tools/classifier/__init__.py`
- `tools/classifier/_policy.py`
- `tools/classifier/_refusal.py`
- `tools/classifier/_inference.py`
- `tools/classifier/_prompt.py`
- `tools/classifier/_context.py`
- `tools/classifier/_analysis.py`
- `tools/classifier/_ci.py`
- `tools/classifier/_audit.py`
- `tests/test_core.py`
- `tests/test_classifier/` (8 test files)
- `tests/test_pressure_scan.py`
- `tests/test_semantic_intent_reframer.py`

**Modified files:**
- `tools/safe_read.py` -- calibration loading replaced
- `tools/safe_write.py` -- calibration loading replaced
- `tools/safe_exec.py` -- calibration loading replaced
- `tools/safe_fetch.py` -- calibration loading replaced
- `tools/safe_input.py` -- calibration loading replaced
- All hooks that do vocab loading -- calibration loading replaced

**Deleted files:**
- `tools/classifier.py` -- replaced by `tools/classifier/` package

# Demo Recorder Production Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Flywheel demo recorder refuse unsafe or unverified publishable output while preserving its offline, zero-dependency transcript/player contract.

**Architecture:** Keep `harness.demo-transcript/v1` readable and add optional evidence fields rather than replacing the schema. Each step resolves its own working directory and allowlisted environment, executes into a unique disposable state root, scrubs every public string, evaluates declared exit/output assertions, and contributes to a transcript-level `publishable` verdict. The player renders the same embedded transcript with the current Telos v2 palette and accessible controls.

**Tech Stack:** Python 3.12 standard library, JSON, subprocess, pytest, self-contained HTML/CSS/JavaScript.

## Global Constraints

- Preserve the current transcript schema string `harness.demo-transcript/v1` and receipt derivation.
- Do not add runtime dependencies or network calls.
- Do not modify the existing dirty files `demos/README.md`, `demos/mneme-showcase/player.html`, `demos/mneme-showcase/transcript.json`, or `demos/scripts/mneme-showcase.json`.
- Default every undeclared step to `expected_exit_codes: [0]`, `expect: []`, `capture: "terminal-replay"`, and no inherited environment outside the Windows/Python process allowlist.
- Redact before hashing, writing, printing, or rendering. A surviving forbidden value makes the transcript non-publishable.
- A failed assertion must still be recorded honestly, but the CLI must return exit code `1`.
- Temporary state must be unique per run and removed after execution; the transcript records only whether cleanup succeeded, never the absolute temp path.
- Public command display uses `display_command` when supplied and must never reveal an execution-only absolute path.
- Existing scripts without the new fields remain executable.

---

### Task 1: Execution context, assertions, redaction, and publishability

**Files:**
- Modify: `scripts/demo_recorder.py`
- Modify: `tests/test_demo_recorder.py`

**Interfaces:**
- Consumes: existing JSON steps with `title`, `command`, and `narration`.
- Produces: `execute_step(step: dict, *, index: int, dry_run: bool, timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS, cwd: Path | None = None, run_temp: Path | None = None, inherited_env: Mapping[str, str] | None = None) -> dict`, transcript fields `publishable`, `cleanup_ok`, and per-step fields `display_command`, `capture`, `assertions`, `assertions_passed`, and `redaction_count`.

- [ ] **Step 1: Add failing tests for defaults, declared assertions, and the CLI gate**

Add tests that prove an undeclared successful step remains publishable, an exit code outside `expected_exit_codes` is recorded with `assertions_passed == False`, a missing literal from `expect` fails, and `main()` returns `1` for a non-publishable transcript. Use only `python -c` commands and `tmp_path`.

```python
def test_expected_exit_and_output_assertions_control_publishability(tmp_path):
    script = write_script(tmp_path, [{
        "title": "Assert output",
        "command": 'python -c "print(\'actual\')"',
        "display_command": "tool inspect --fixture public.json",
        "narration": "The public fixture produces a checkable value.",
        "expected_exit_codes": [0],
        "expect": ["required"],
    }])
    result = record_demo(script, "assert-demo", out_root=tmp_path / "demos")
    step = result["transcript"]["steps"][0]
    assert step["command"] == "tool inspect --fixture public.json"
    assert step["assertions_passed"] is False
    assert step["assertions"]["missing"] == ["required"]
    assert result["transcript"]["publishable"] is False


def test_main_returns_one_when_publish_gate_fails(tmp_path):
    script = write_script(tmp_path, [{
        "title": "Expected refusal",
        "command": 'python -c "import sys; sys.exit(4)"',
        "narration": "Unexpected failure blocks publication.",
    }])
    assert main([
        "--script", str(script), "--name", "blocked",
        "--out-root", str(tmp_path / "demos"),
    ]) == 1
```

- [ ] **Step 2: Run the focused tests and confirm they fail for missing behavior**

Run: `python -m pytest tests/test_demo_recorder.py -q`

Expected: the new assertions fail because the transcript has no publishability or assertion metadata and `main()` always returns `0`.

- [ ] **Step 3: Add execution-context and assertion helpers**

Implement these exact contracts in `scripts/demo_recorder.py`:

```python
SAFE_ENV_KEYS = {"COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}
CAPTURE_TYPES = {"terminal-replay", "browser-video", "native-video"}


def _resolve_step_cwd(step: dict, default_cwd: Path) -> Path:
    configured = step.get("cwd")
    path = Path(configured).expanduser() if configured else default_cwd
    path = path if path.is_absolute() else default_cwd / path
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"step cwd is not a directory: {configured or default_cwd}")
    return resolved


def _build_step_env(step: dict, inherited_env: Mapping[str, str]) -> dict[str, str]:
    names = SAFE_ENV_KEYS | set(step.get("env_allowlist", []))
    return {name: inherited_env[name] for name in sorted(names) if name in inherited_env}


def _evaluate_assertions(step: dict, exit_code: int, output: str) -> dict:
    expected = step.get("expected_exit_codes", [0])
    required = step.get("expect", [])
    missing = [value for value in required if value not in output]
    return {
        "expected_exit_codes": expected,
        "exit_code_ok": exit_code in expected,
        "required": required,
        "missing": missing,
        "passed": exit_code in expected and not missing,
    }
```

Validate that `expected_exit_codes` is a non-empty list of integers, `expect`, `env_allowlist`, and `redact_patterns` are lists of non-empty strings, and `capture` is one of `CAPTURE_TYPES` during `load_demo_script()`.

- [ ] **Step 4: Add failing tests for built-in and explicit redaction**

```python
def test_sensitive_values_are_redacted_before_hash_and_render(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_SECRET", "ghp_abcdefghijklmnopqrstuvwxyz1234567890")
    script = write_script(tmp_path, [{
        "title": "Scrub output",
        "command": 'python -c "import os; print(\'person@example.com\'); print(os.environ[\'DEMO_SECRET\'])"',
        "display_command": "tool inspect C:\\Users\\PrivateName\\fixture.json",
        "narration": "The private marker PRIVATE-CUSTOM never leaves the recorder.",
        "env_allowlist": ["DEMO_SECRET"],
        "redact_patterns": ["PRIVATE-CUSTOM"],
    }])
    result = record_demo(script, "scrub-demo", out_root=tmp_path / "demos")
    serialized = json.dumps(result["transcript"])
    html_text = Path(result["player_path"]).read_text(encoding="utf-8")
    for forbidden in ("person@example.com", "ghp_", "PrivateName", "PRIVATE-CUSTOM"):
        assert forbidden not in serialized
        assert forbidden not in html_text
    assert result["transcript"]["steps"][0]["redaction_count"] >= 4
```

- [ ] **Step 5: Implement redaction before receipt generation**

Create `scrub_text(text: str, explicit_patterns: Sequence[str] = ()) -> tuple[str, int]`. Apply concrete home-directory and username replacements first, then case-insensitive email, Windows absolute-path, Bearer token, OpenAI token, GitHub token, and credential-assignment patterns, followed by `re.escape()` for each explicit pattern. Use the stable replacement labels `[redacted-home]`, `[redacted-email]`, `[redacted-path]`, `[redacted-token]`, `[redacted-credential]`, and `[redacted-explicit]`. Scrub `title`, `narration`, the displayed command, stdout, stderr, and combined output before calculating `output_sha256`.

- [ ] **Step 6: Create unique temporary state and cleanup evidence**

Wrap step execution in `tempfile.TemporaryDirectory(prefix=f"demo-{name}-")`. Pass its `Path` to every step as `run_temp`; replace the literal token `{demo_temp}` in execution commands and `cwd`, but never in `display_command`. On normal context-manager exit set `cleanup_ok = True`. If cleanup raises, retain the transcript, set `cleanup_ok = False`, set `publishable = False`, and omit the absolute path from the serialized result.

- [ ] **Step 7: Calculate transcript publishability and CLI exit status**

Set `publishable` to true only when every step has `assertions_passed`, no forbidden value survives the post-scrub scan, and cleanup succeeds. Print `publishable: yes|no` in `main()`, then return `0 if transcript["publishable"] else 1`.

- [ ] **Step 8: Run recorder tests**

Run: `python -m pytest tests/test_demo_recorder.py -q`

Expected: all existing and new recorder tests pass.

- [ ] **Step 9: Run diff and secret-shape checks**

Run:

```powershell
git diff --check -- scripts/demo_recorder.py tests/test_demo_recorder.py
git diff -- scripts/demo_recorder.py tests/test_demo_recorder.py | Select-String -Pattern 'ghp_|sk-[A-Za-z0-9]|C:\\Users\\' -CaseSensitive
```

Expected: `git diff --check` returns zero. The second command shows only the deliberately synthetic test fixtures and no real credential or home path.

### Task 2: Telos v2 offline player and media-package manifest

**Files:**
- Modify: `scripts/demo_player_html.py`
- Create: `scripts/demo_package.py`
- Modify: `tests/test_demo_recorder.py`
- Create: `tests/test_demo_package.py`

**Interfaces:**
- Consumes: a publishable `transcript.json` plus optional full/short video, captions, and poster files.
- Produces: self-contained accessible player HTML and `demo-package.json` with relative paths, SHA-256 hashes, byte sizes, capture type, source revision, and transcript receipt.

- [ ] **Step 1: Add failing player-structure tests**

Assert the generated player contains a skip link, `aria-live="polite"`, a visible `:focus-visible` rule, `prefers-reduced-motion`, Hanken Grotesk/system sans for UI, a separate mono readout stack, no `border-left: 3px`, and no external URL attributes.

- [ ] **Step 2: Restyle the player to the existing Telos v2 contract**

Use a calm deep-plum ground, near-white ink, muted lavender readouts, one cyan signal, one amber warning, and one red failure color. UI copy uses `"Hanken Grotesk", "Segoe UI", sans-serif`; terminal output uses `"Conso", "Cascadia Mono", Consolas, monospace`. Replace the caption side stripe with a full 1px border and 8px radius. Keep content visible without animation and stop cursor blinking under reduced motion.

- [ ] **Step 3: Add failing package-manifest tests**

Create a temporary publishable transcript and dummy `full.webm`, `short.webm`, `captions.vtt`, and `poster.png`. Assert `build_demo_package()` rejects a non-publishable transcript, rejects missing files, emits only relative paths, includes SHA-256/byte size for every artifact, and records the source revision supplied by the caller.

- [ ] **Step 4: Implement the zero-dependency package builder**

`scripts/demo_package.py` exposes:

```python
PACKAGE_SCHEMA = "harness.demo-package/v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_demo_package(
    demo_dir: Path,
    *,
    source_revision: str,
    artifacts: Mapping[str, Path],
) -> dict:
    root = demo_dir.resolve()
    required = {
        "transcript", "player", "full_video", "short_video", "captions", "poster"
    }
    if set(artifacts) != required:
        raise ValueError(f"artifact roles must be exactly {sorted(required)}")

    resolved: dict[str, Path] = {}
    for role, configured in artifacts.items():
        path = configured.resolve()
        if not path.is_file() or not path.is_relative_to(root):
            raise ValueError(f"{role} must be a file inside {root.name}")
        resolved[role] = path

    transcript = json.loads(resolved["transcript"].read_text(encoding="utf-8"))
    if transcript.get("publishable") is not True:
        raise ValueError("transcript is not publishable")

    manifest = {
        "schema": PACKAGE_SCHEMA,
        "name": transcript.get("name", root.name),
        "source_revision": source_revision,
        "capture": sorted({step.get("capture", "terminal-replay") for step in transcript["steps"]}),
        "transcript_receipt_sha256": transcript["receipt_sha256"],
        "artifacts": {
            role: {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for role, path in sorted(resolved.items())
        },
    }
    (root / "demo-package.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return manifest
```

Require artifact roles `transcript`, `player`, `full_video`, `short_video`, `captions`, and `poster`. Resolve every artifact and require it to stay within `demo_dir`. Read `transcript`, require `publishable is True`, hash files in 1 MiB chunks, write `demo-package.json`, and return the manifest.

- [ ] **Step 5: Run focused tests and syntax checks**

Run:

```powershell
python -m pytest tests/test_demo_recorder.py tests/test_demo_package.py -q
python -m py_compile scripts/demo_recorder.py scripts/demo_player_html.py scripts/demo_package.py
git diff --check -- scripts/demo_recorder.py scripts/demo_player_html.py scripts/demo_package.py tests/test_demo_recorder.py tests/test_demo_package.py
```

Expected: all tests pass, compilation returns zero, and the diff check is clean.

- [ ] **Step 6: Commit only the scoped implementation**

```powershell
git add scripts/demo_recorder.py scripts/demo_player_html.py scripts/demo_package.py tests/test_demo_recorder.py tests/test_demo_package.py docs/superpowers/plans/2026-07-12-demo-recorder-production-gates.md
git commit -m "feat: gate demo packages on verified safe output"
```

Do not stage or commit any pre-existing dirty demo files.

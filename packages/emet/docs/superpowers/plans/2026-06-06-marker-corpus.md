# Marker Corpus Reconciliation -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make EMET `refuse` and the `monitor` census re-derive identical marker verdicts across the Python and Rust implementations by loading a single versioned, sha-pinned, plain-text corpus and applying one literal ASCII-case-insensitive byte-scan.

**Architecture:** New stdlib-only `corpus.py` core module (load/match/redact) shared by `membrane.py` and `monitor.py`; `impl/rust/emet.rs` implements the same logic inline. The corpus is `conformance/markers.corpus`, resolved by a default path next to the tool or the `EMET_CORPUS` env override; refuse/monitor echo `corpus_version` + `corpus_sha256`; a missing corpus is `UNVERIFIABLE reason=E_NO_CORPUS`. The byte-hash core is untouched.

**Tech Stack:** Python 3 stdlib (hashlib, os), Rust std only, JSON conformance vectors.

**Spec:** docs/superpowers/specs/2026-06-06-marker-corpus-design.md

**Commit policy note:** The operator commits only when asked, and `emet` is on its default branch. Before executing, create a branch (e.g. `git checkout -b design/marker-corpus`). The `Commit` steps below are real but gated on the operator's go-ahead; batch or defer them per the operator's instruction.

**Decision recorded during brainstorming:** uniform separator variants (underscore / space / none, plus the hyphen form for `authority-pill`) are applied to ALL multi-token markers, including `consulting register` and `canonical recipients`. This slightly broadens two markers vs the old regex (which required a separator); accepted under the uniform-variants decision.

**Compiler note:** There is no `rustc` in the authoring environment. Task 6 (Rust) is verified by CI on push, not locally. All other tasks are fully verifiable with `python`.

---

## File structure

- Create: `corpus.py` -- corpus loader, matcher, redactor (stdlib-only core module).
- Create: `conformance/markers.corpus` -- the versioned marker artifact.
- Create: `test_corpus.py` -- unit tests for `corpus.py`.
- Create: `test_monitor.py` -- behavior tests for `monitor.py` report/corpus handling.
- Modify: `membrane.py` -- refuse() uses corpus.py; remove `AUTHORITY`/`AUTHORITY_RE`; drop unused `re` import.
- Modify: `monitor.py` -- report() uses corpus.py; remove `MARKERS`/`_markers`; drop unused `re` import.
- Modify: `impl/rust/emet.rs` -- load corpus from file; remove `const MARKERS`; thread markers through.
- Modify: `conformance/run.py` -- set `EMET_CORPUS` for both impls; add per-vector `env`.
- Modify: `conformance/vectors.json` -- corpus_version 0->1, add corpus_sha256, add 3 vectors.
- Modify: `SPEC.md` -- sections 8, 10, 13, 16.
- Modify: `README.md`, `CONTRIBUTING.md`, `.github/workflows/conformance.yml`, `impl/rust/README.md` -- counts + corpus mention + new CI test steps.

---

## Task 1: corpus.py loader, matcher, redactor

**Files:**
- Create: `corpus.py`
- Test: `test_corpus.py`

- [ ] **Step 1: Write the failing tests**

Create `test_corpus.py`:

```python
#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""test_corpus.py - unit tests for the shared marker corpus module."""
import os, sys, tempfile, shutil, hashlib, unittest, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CORPUS_TEXT = (
    b"# corpus_version: 7\n"
    b"# a comment line\n"
    b"\n"
    b"ground_truth_canonical\n"
    b"ground truth canonical\n"
    b"authority-pill\n"
)

class CorpusModule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="corpus_test_")
        self.cpath = os.path.join(self.tmp, "markers.corpus")
        with open(self.cpath, "wb") as f:
            f.write(CORPUS_TEXT)
        os.environ["EMET_CORPUS"] = self.cpath
        import corpus
        importlib.reload(corpus)
        self.corpus = corpus
    def tearDown(self):
        os.environ.pop("EMET_CORPUS", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_parses_version_comments_blanks(self):
        v, sha, markers = self.corpus.load()
        self.assertEqual(v, 7)
        self.assertEqual(sha, hashlib.sha256(CORPUS_TEXT).hexdigest())
        self.assertEqual(markers, [b"ground_truth_canonical",
                                   b"ground truth canonical",
                                   b"authority-pill"])

    def test_scan_counts_case_insensitive_and_space_form(self):
        v, sha, markers = self.corpus.load()
        hits, clean = self.corpus.scan(b"see GROUND TRUTH CANONICAL here\n", markers)
        self.assertEqual(len(hits), 1)
        self.assertIn(b"[REFUSED-IN-BAND-AUTHORITY]", clean)
        self.assertNotIn(b"GROUND TRUTH CANONICAL", clean)

    def test_scan_preserves_non_ascii_bytes(self):
        v, sha, markers = self.corpus.load()
        payload = b"\xe2\x84\xaa authority-pill\n"  # U+212A KELVIN then a marker
        hits, clean = self.corpus.scan(payload, markers)
        self.assertEqual(len(hits), 1)
        self.assertTrue(clean.startswith(b"\xe2\x84\xaa "))

    def test_missing_corpus_raises_e_no_corpus(self):
        os.environ["EMET_CORPUS"] = os.path.join(self.tmp, "nope.corpus")
        importlib.reload(self.corpus)
        with self.assertRaises(self.corpus.CorpusError) as cm:
            self.corpus.load()
        self.assertEqual(cm.exception.reason, "E_NO_CORPUS")

    def test_count_helper_matches_scan(self):
        v, sha, markers = self.corpus.load()
        b = b"authority-pill and ground_truth_canonical\n"
        self.assertEqual(self.corpus.count(b, markers), 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_corpus.py`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'corpus'`.

- [ ] **Step 3: Write corpus.py**

Create `corpus.py`:

```python
#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""corpus.py - EMET marker corpus loader and matcher (shared core).

The marker denylist is a versioned, sha-pinned DATA artifact (SPEC sections 8 and
16), loaded identically by membrane.py (refuse) and monitor.py (census). Matching
is literal ASCII-case-insensitive substring over RAW BYTES - no regex - so an
independent implementation re-derives identical counts. The byte-hash core does
NOT depend on this module (SPEC section 8).
"""
import os, hashlib

DEFAULT_NAME = "markers.corpus"
REPL = b"[REFUSED-IN-BAND-AUTHORITY]"

class CorpusError(Exception):
    """Inability to load the corpus; .reason is a stable machine code."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

def corpus_path():
    env = os.environ.get("EMET_CORPUS")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "conformance", DEFAULT_NAME)

def load():
    """Return (version:int, sha256_hex:str, markers:list[bytes] lowercased).
    Raise CorpusError('E_NO_CORPUS') if unreadable, ('E_NO_CORPUS_VERSION') if the
    header is absent."""
    path = corpus_path()
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        raise CorpusError("E_NO_CORPUS")
    sha = hashlib.sha256(data).hexdigest()
    version = None
    markers = []
    for line in data.split(b"\n"):
        if line.endswith(b"\r"):
            line = line[:-1]
        if line[:1] == b"#":
            meta = line[1:].strip()
            if version is None and meta[:15].lower() == b"corpus_version:":
                try:
                    version = int(meta[15:].strip())
                except ValueError:
                    pass
            continue
        if line.strip() == b"":
            continue
        markers.append(line.lower())  # bytes.lower() is ASCII-only
    if version is None:
        raise CorpusError("E_NO_CORPUS_VERSION")
    return version, sha, markers

def _alower(b):
    return b + 32 if 65 <= b <= 90 else b

def matches_at(hay, i, m):
    if i + len(m) > len(hay):
        return False
    for j in range(len(m)):
        if _alower(hay[i + j]) != m[j]:
            return False
    return True

def scan(hay, markers):
    """Non-overlapping leftmost scan in corpus order.
    Return (hits, redacted_bytes) where hits is a list of (offset, length)."""
    out = bytearray()
    hits = []
    i = 0
    n = len(hay)
    while i < n:
        ln = 0
        for m in markers:
            if m and matches_at(hay, i, m):
                ln = len(m)
                break
        if ln:
            hits.append((i, ln))
            out += REPL
            i += ln
        else:
            out.append(hay[i])
            i += 1
    return hits, bytes(out)

def count(hay, markers):
    return len(scan(hay, markers)[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python test_corpus.py`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Commit**

```bash
git add corpus.py test_corpus.py
git commit -m "feat(corpus): shared stdlib marker corpus loader + byte-scan matcher"
```

---

## Task 2: Ship the corpus artifact

**Files:**
- Create: `conformance/markers.corpus`
- Test: `test_corpus.py` (add one test that loads the SHIPPED corpus via default path)

- [ ] **Step 1: Write the failing test**

Add to `test_corpus.py` class `CorpusModule`:

```python
    def test_shipped_corpus_loads_at_version_1(self):
        os.environ.pop("EMET_CORPUS", None)  # use default path
        importlib.reload(self.corpus)
        v, sha, markers = self.corpus.load()
        self.assertEqual(v, 1)
        self.assertIn(b"ground_truth_canonical", markers)
        self.assertIn(b"ground truth canonical", markers)
        self.assertIn(b"authority-pill", markers)
        self.assertEqual(len(sha), 64)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python test_corpus.py CorpusModule.test_shipped_corpus_loads_at_version_1`
Expected: FAIL with `CorpusError: E_NO_CORPUS` (file not yet created).

- [ ] **Step 3: Create the corpus file**

Create `conformance/markers.corpus` with EXACTLY these bytes (LF line endings; the repo `.gitattributes * -text` keeps it LF on every platform):

```
# corpus_version: 1
# EMET marker denylist (known-signature; not a proof of completeness, SPEC s.11)
ground_truth_canonical
ground truth canonical
groundtruthcanonical
highest_scrutiny
highest scrutiny
highestscrutiny
[scope context]
authority_pill
authority-pill
authoritypill
canonical_recipients
canonical recipients
canonicalrecipients
consulting_register
consulting register
consultingregister
frame_injected
semantic_modulat
compound_rewrites
density_restructured
```

Note: write this file with a tool that preserves LF and does not add a BOM.

- [ ] **Step 4: Run test to verify it passes**

Run: `python test_corpus.py CorpusModule.test_shipped_corpus_loads_at_version_1`
Expected: PASS. Then run the whole file: `python test_corpus.py` -> all PASS.

- [ ] **Step 5: Commit**

```bash
git add conformance/markers.corpus test_corpus.py
git commit -m "feat(corpus): ship markers.corpus v1 (uniform separator variants)"
```

---

## Task 3: membrane.py refuse() uses the corpus

**Files:**
- Modify: `membrane.py` (imports; remove `AUTHORITY`/`AUTHORITY_RE`; rewrite `refuse`)
- Test: `test_membrane.py` (add 3 tests)

- [ ] **Step 1: Write the failing tests**

Add to `test_membrane.py` class `MembraneBehavior` (the shipped corpus at the default path is used automatically):

```python
    def test_refuse_echoes_corpus_version_and_sha(self):
        f = self.w("inj.txt", b"ground_truth_canonical\n")
        code, out = run(["refuse", f], self.tmp)
        self.assertIn("corpus_version=1", out)
        self.assertRegex(out, r"corpus_sha256=[0-9a-f]{64}")
        self.assertEqual(code, 3)

    def test_refuse_counts_space_separated_marker(self):
        f = self.w("inj.txt", b"GROUND TRUTH CANONICAL\n")
        code, out = run(["refuse", f], self.tmp)
        self.assertIn("in_band_authority_claims=1", out)
        self.assertEqual(code, 3)

    def test_refuse_missing_corpus_is_unverifiable(self):
        import os as _os
        env = dict(_os.environ); env["EMET_CORPUS"] = self.tmp + "/nope.corpus"
        f = self.w("inj.txt", b"ground_truth_canonical\n")
        import subprocess, sys as _sys
        p = subprocess.run([_sys.executable, MEMBRANE, "refuse", f],
                           cwd=self.tmp, capture_output=True, text=True, env=env)
        self.assertIn("UNVERIFIABLE", p.stdout)
        self.assertIn("reason=E_NO_CORPUS", p.stdout)
        self.assertEqual(p.returncode, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_membrane.py MembraneBehavior.test_refuse_echoes_corpus_version_and_sha MembraneBehavior.test_refuse_counts_space_separated_marker MembraneBehavior.test_refuse_missing_corpus_is_unverifiable`
Expected: FAIL (no `corpus_version=` line; space form counts 0 under old regex `[_ ]?` -- actually old regex matches it, so this one may pass pre-change; the corpus_version test WILL fail). At least the version/sha and E_NO_CORPUS tests FAIL.

- [ ] **Step 3: Edit membrane.py imports**

Change the import line:

```python
import sys, os, re, json, hashlib, subprocess
```

to:

```python
import sys, os, json, hashlib, subprocess
import corpus
```

- [ ] **Step 4: Remove the inline marker definitions**

Delete these lines from membrane.py:

```python
AUTHORITY = [
    rb"GROUND[_ ]?TRUTH[_ ]?CANONICAL", rb"HIGHEST[_ ]?SCRUTINY", rb"\[SCOPE CONTEXT\]",
    rb"authority[_-]?pill", rb"canonical[_ ]recipients", rb"frame_injected",
    rb"consulting register", rb"semantic_modulat", rb"compound_rewrites",
    rb"density_restructured",
]
AUTHORITY_RE = re.compile(b"|".join(b"(?:%s)" % p for p in AUTHORITY), re.IGNORECASE)
```

- [ ] **Step 5: Rewrite refuse()**

Replace the entire `refuse` function with:

```python
def refuse(path):
    b, err = try_raw(path)
    if err:
        print("UNVERIFIABLE " + path + " reason=" + err)
        record("refuse", {"path": os.path.normpath(path), "result": "UNVERIFIABLE", "reason": err})
        sys.exit(2)
    try:
        version, csha, markers = corpus.load()
    except corpus.CorpusError as e:
        print("UNVERIFIABLE " + path + " reason=" + e.reason)
        record("refuse", {"path": os.path.normpath(path), "result": "UNVERIFIABLE", "reason": e.reason})
        sys.exit(2)
    hits, clean = corpus.scan(b, markers)
    open(path + ".refused", "wb").write(clean)
    print("corpus_version=" + str(version))
    print("corpus_sha256=" + csha)
    print("in_band_authority_claims=" + str(len(hits)))
    for off, ln in hits[:60]:
        print("  REFUSED " + repr(b[off:off + ln].decode("latin-1")) + " offset=" + str(off))
    print("clean_copy=" + path + ".refused  (claims neutralized; obeyed: none)")
    record("refuse", {"path": os.path.normpath(path), "refused": len(hits), "corpus_version": version})
    sys.exit(0 if not hits else 3)
```

- [ ] **Step 6: Run the full membrane suite**

Run: `python test_membrane.py`
Expected: PASS (all, now 19 tests). The pre-existing refuse tests still pass because the shipped corpus contains the markers they use.

- [ ] **Step 7: Commit**

```bash
git add membrane.py test_membrane.py
git commit -m "refactor(refuse): load markers from corpus; echo corpus_version/sha; E_NO_CORPUS"
```

---

## Task 4: monitor.py report() uses the corpus

**Files:**
- Modify: `monitor.py` (imports; remove `MARKERS`/`_markers`; rewrite `report`)
- Test: `test_monitor.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `test_monitor.py`:

```python
#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""test_monitor.py - behavior proof for monitor.py corpus handling."""
import os, sys, json, tempfile, shutil, subprocess, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MONITOR = os.path.join(HERE, "monitor.py")

class MonitorBehavior(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="monitor_test_")
        self.target = os.path.join(self.tmp, "t.txt")
        with open(self.target, "wb") as f:
            f.write(b"ground_truth_canonical\n")
        import hashlib
        h = hashlib.sha256(b"ground_truth_canonical\n").hexdigest()
        self.manifest = os.path.join(self.tmp, "m.json")
        with open(self.manifest, "w", encoding="utf-8") as f:
            json.dump({self.target: h}, f)
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    def run_mon(self, args, env=None):
        p = subprocess.run([sys.executable, MONITOR] + args, cwd=self.tmp,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout

    def test_report_echoes_corpus_version_and_sha(self):
        code, out = self.run_mon(["report", self.manifest])
        self.assertIn("corpus_version=1", out)
        self.assertRegex(out, r"corpus_sha256=[0-9a-f]{64}")

    def test_report_missing_corpus_is_unverifiable(self):
        env = dict(os.environ); env["EMET_CORPUS"] = self.tmp + "/nope.corpus"
        code, out = self.run_mon(["report", self.manifest], env=env)
        self.assertIn("UNVERIFIABLE", out)
        self.assertIn("reason=E_NO_CORPUS", out)
        self.assertEqual(code, 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python test_monitor.py`
Expected: FAIL (no `corpus_version=` in output; missing-corpus path not handled).

- [ ] **Step 3: Edit monitor.py imports**

Change:

```python
import sys, os, json, re, hashlib
```

to:

```python
import sys, os, json, hashlib
import corpus
```

- [ ] **Step 4: Remove MARKERS and _markers()**

Delete the `MARKERS = [...]` list and the `def _markers(b): ...` function from monitor.py.

- [ ] **Step 5: Rewrite report()**

Replace the entire `report` function with:

```python
def report(manifest):
    db = json.load(open(manifest, encoding="utf-8"))
    try:
        version, csha, markers = corpus.load()
    except corpus.CorpusError as e:
        print("=== EXTERNAL ACCOUNTABILITY REPORT ===")
        print("baseline: " + manifest)
        print("corpus=UNVERIFIABLE reason=" + e.reason)
        _record(manifest, "report", {"result": "UNVERIFIABLE", "reason": e.reason})
        sys.exit(2)
    drift = missing = total = 0
    print("=== EXTERNAL ACCOUNTABILITY REPORT ===")
    print("baseline: " + manifest)
    print("corpus_version=" + str(version) + " corpus_sha256=" + csha)
    for p in sorted(db):
        want = db[p]
        if not os.path.isfile(p):
            print("MISSING  markers=  -  " + p.split(chr(92))[-1]); missing += 1; continue
        b = open(p, "rb").read(); got = sha(b); hits = corpus.count(b, markers); total += hits
        st = "MATCH " if got == want else "DRIFT "
        if got != want: drift += 1
        print(st + " markers=" + str(hits).rjust(3) + "  " + p.split(chr(92))[-1])
    verdict = "INTACT" if drift == 0 and missing == 0 else "CHANGED"
    print("files=" + str(len(db)) + " drift=" + str(drift) + " missing=" + str(missing) + " markers=" + str(total) + " baseline=" + verdict)
    _record(manifest, "report", {"files": len(db), "drift": drift, "missing": missing, "markers": total, "verdict": verdict, "corpus_version": version})
    sys.exit(0 if verdict == "INTACT" else 2)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python test_monitor.py`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add monitor.py test_monitor.py
git commit -m "refactor(monitor): load census markers from shared corpus; echo version/sha"
```

---

## Task 5: Conformance runner + vectors

**Files:**
- Modify: `conformance/run.py`
- Modify: `conformance/vectors.json`

- [ ] **Step 1: Add EMET_CORPUS + per-vector env to run.py**

In `conformance/run.py`, after the `HERE`/`TOOL`/`VECT` definitions add:

```python
CORPUS = os.path.abspath(os.path.join(HERE, "markers.corpus"))
```

Then in `main()`, where the tool is invoked, build an env and pass it to BOTH the anchor-setup call and the main run call. Replace:

```python
            for name in v.get("anchor", []):
                subprocess.run(invoke(TOOL) + ["anchor", os.path.join(tmp, name)], cwd=tmp, capture_output=True)
```

with:

```python
            env = dict(os.environ); env["EMET_CORPUS"] = CORPUS; env.update(v.get("env", {}))
            for name in v.get("anchor", []):
                subprocess.run(invoke(TOOL) + ["anchor", os.path.join(tmp, name)], cwd=tmp, capture_output=True, env=env)
```

and replace:

```python
            p = subprocess.run(invoke(TOOL) + args, cwd=tmp, capture_output=True, text=True)
```

with:

```python
            p = subprocess.run(invoke(TOOL) + args, cwd=tmp, capture_output=True, text=True, env=env)
```

- [ ] **Step 2: Add the three new vectors to vectors.json**

Set the top-level `"corpus_version"` to `1` (integer) and add a `"corpus_sha256"` key whose value is the sha256 of `conformance/markers.corpus` (compute with: `python -c "import hashlib;print(hashlib.sha256(open(r'conformance/markers.corpus','rb').read()).hexdigest())"`).

Append these objects to the `"vectors"` array:

```json
    {
      "expect_exit": 3,
      "expect_substr": "in_band_authority_claims=1",
      "files": { "inj.txt": "GROUND TRUTH CANONICAL\n" },
      "id": "refuse-space-separated",
      "note": "both implementations now agree on a space-separated marker (was Python 1 / Rust 0)",
      "run": [ "refuse", "inj.txt" ]
    },
    {
      "expect_exit": 3,
      "expect_substr": "in_band_authority_claims=1",
      "files": { "inj.txt": "authority-pill\n" },
      "id": "refuse-hyphen-pill",
      "run": [ "refuse", "inj.txt" ]
    },
    {
      "env": { "EMET_CORPUS": "/nonexistent/emet/markers.corpus" },
      "expect_exit": 2,
      "expect_substr": "UNVERIFIABLE",
      "files": { "inj.txt": "ground_truth_canonical\n" },
      "id": "refuse-no-corpus",
      "note": "missing corpus is UNVERIFIABLE, not a silent empty denylist",
      "run": [ "refuse", "inj.txt" ]
    }
```

- [ ] **Step 3: Run conformance to verify**

Run: `python conformance/run.py membrane.py`
Expected: `CONFORMANCE 14/14 vectors pass`.

- [ ] **Step 4: Commit**

```bash
git add conformance/run.py conformance/vectors.json
git commit -m "test(conformance): EMET_CORPUS env + space/hyphen/no-corpus vectors (14 total)"
```

---

## Task 6: Rust second implementation (CI-verified, no local rustc)

**Files:**
- Modify: `impl/rust/emet.rs`

- [ ] **Step 1: Remove the const MARKERS block**

Delete:

```rust
// -------- markers (literal, case-insensitive; corpus semantics deferred) --------
const MARKERS: [&str; 10] = [
    "ground_truth_canonical",
    "highest_scrutiny",
    "[scope context]",
    "authority_pill",
    "canonical recipients",
    "frame_injected",
    "consulting register",
    "semantic_modulat",
    "compound_rewrites",
    "density_restructured",
];
```

- [ ] **Step 2: Add the corpus loader**

Immediately above `fn matches_marker_at`, add:

```rust
// -------- marker corpus (loaded from a versioned data artifact) --------
fn corpus_path() -> Option<String> {
    if let Ok(p) = env::var("EMET_CORPUS") {
        return Some(p);
    }
    let exe = env::current_exe().ok()?;
    let dir = exe.parent()?;
    Some(dir.join("markers.corpus").to_string_lossy().to_string())
}

fn load_corpus() -> Result<(i64, String, Vec<Vec<u8>>), &'static str> {
    let path = corpus_path().ok_or("E_NO_CORPUS")?;
    let data = fs::read(&path).map_err(|_| "E_NO_CORPUS")?;
    let sha = sha256_hex(&data);
    let mut version: Option<i64> = None;
    let mut markers: Vec<Vec<u8>> = Vec::new();
    for raw in data.split(|&b| b == b'\n') {
        let line: &[u8] = if raw.last() == Some(&b'\r') { &raw[..raw.len() - 1] } else { raw };
        if line.first() == Some(&b'#') {
            let meta: Vec<u8> = line[1..].iter().cloned()
                .skip_while(|&c| c == b' ' || c == b'\t').collect();
            let lower: Vec<u8> = meta.iter().map(|b| b.to_ascii_lowercase()).collect();
            if version.is_none() && lower.starts_with(b"corpus_version:") {
                let rest = String::from_utf8_lossy(&meta[b"corpus_version:".len()..]);
                if let Ok(v) = rest.trim().parse::<i64>() {
                    version = Some(v);
                }
            }
            continue;
        }
        if line.iter().all(|&c| c == b' ' || c == b'\t') {
            continue;
        }
        markers.push(line.iter().map(|b| b.to_ascii_lowercase()).collect());
    }
    match version {
        Some(v) => Ok((v, sha, markers)),
        None => Err("E_NO_CORPUS_VERSION"),
    }
}
```

- [ ] **Step 3: Thread markers through the matcher**

Replace `fn marker_len_at(bytes: &[u8], i: usize) -> usize { ... }` with:

```rust
fn marker_len_at(bytes: &[u8], i: usize, markers: &[Vec<u8>]) -> usize {
    for m in markers {
        if matches_marker_at(bytes, i, m) {
            return m.len();
        }
    }
    0
}
```

Delete the old `fn count_markers(bytes: &[u8]) -> usize { ... }` (its scan moves into cmd_refuse).

- [ ] **Step 4: Rewrite cmd_refuse**

Replace the whole `cmd_refuse` function with:

```rust
fn cmd_refuse(path: &str) -> i32 {
    let bytes = match fs::read(path) {
        Ok(b) => b,
        Err(_) => {
            println!("UNVERIFIABLE {} reason=E_NOT_FOUND", path);
            return 2;
        }
    };
    let (version, csha, markers) = match load_corpus() {
        Ok(c) => c,
        Err(reason) => {
            println!("UNVERIFIABLE {} reason={}", path, reason);
            return 2;
        }
    };
    let repl = b"[REFUSED-IN-BAND-AUTHORITY]";
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut n = 0usize;
    let mut i = 0;
    while i < bytes.len() {
        let hit = marker_len_at(&bytes, i, &markers);
        if hit > 0 {
            out.extend_from_slice(repl);
            i += hit;
            n += 1;
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    let _ = fs::write(format!("{}.refused", path), &out);
    println!("corpus_version={}", version);
    println!("corpus_sha256={}", csha);
    println!("in_band_authority_claims={}", n);
    println!("clean_copy={}.refused  (claims neutralized; obeyed: none)", path);
    if n == 0 {
        0
    } else {
        3
    }
}
```

- [ ] **Step 5: Static self-check (no compiler available)**

Read the changed regions and confirm: no remaining reference to `MARKERS` or the old `count_markers`; `marker_len_at` callers pass `&markers`; `env` and `fs` are already imported at the top of the file (they are). Note in the commit message that compilation is CI-verified.

- [ ] **Step 6: Commit**

```bash
git add impl/rust/emet.rs
git commit -m "feat(rust): load marker corpus from artifact; echo version/sha (CI-verified)"
```

---

## Task 7: Spec, docs, and CI

**Files:**
- Modify: `SPEC.md`, `README.md`, `CONTRIBUTING.md`, `impl/rust/README.md`, `.github/workflows/conformance.yml`

- [ ] **Step 1: SPEC.md section 8** -- replace the section-8 body with text that adds: "The corpus is the plain-text artifact conformance/markers.corpus: a `# corpus_version: N` header line, `#` comment lines, blank lines ignored, one literal marker per remaining line. corpus_sha256 is sha256 over the whole file. Matching is literal ASCII-case-insensitive substring over raw bytes. Implementations MUST echo corpus_version and SHOULD echo corpus_sha256 with marker-dependent output."

- [ ] **Step 2: SPEC.md section 10** -- change "The core (membrane, organs, monitor) MUST depend only on..." to "The core (membrane, organs, monitor, corpus) MUST depend only on...".

- [ ] **Step 3: SPEC.md section 13** -- in the refuse grammar bullet, add: "and a line containing corpus_version=N and a line containing corpus_sha256=<hex>."

- [ ] **Step 4: SPEC.md section 16** -- replace with a reference to conformance/markers.corpus as the governed artifact, the plain-text format, and literal ASCII-CI matching; keep the known-signature/non-complete caveat.

- [ ] **Step 5: Update counts and CI**

In `.github/workflows/conformance.yml`: change `behavior proof (16 tests)` to `behavior proof (19 tests)`; change both `expect 11 of 11` to `expect 14 of 14`; add two steps to the `python-reference` job after the behavior-proof step:

```yaml
      - name: corpus unit tests
        run: python test_corpus.py
      - name: monitor behavior tests
        run: python test_monitor.py
```

In `README.md`: change the three `11`/`11/11` count references to `14`/`14/14`, and add a one-line bullet under "What's here": "- A versioned marker corpus (`conformance/markers.corpus`) both implementations load and re-derive identically."

In `CONTRIBUTING.md`: change `reference conformance (11/11)` to `reference conformance (14/14)` and `behavior proof (16 tests)` to `behavior proof (19 tests)`.

In `impl/rust/README.md`: change `CONFORMANCE 11/11 vectors pass` to `CONFORMANCE 14/14 vectors pass`.

- [ ] **Step 6: Full verification**

Run each and confirm:
- `python test_membrane.py` -> OK (19 tests)
- `python test_corpus.py` -> OK (6 tests)
- `python test_monitor.py` -> OK (2 tests)
- `python conformance/run.py membrane.py` -> `CONFORMANCE 14/14 vectors pass`

- [ ] **Step 7: Commit**

```bash
git add SPEC.md README.md CONTRIBUTING.md impl/rust/README.md .github/workflows/conformance.yml
git commit -m "docs(spec): corpus artifact in SPEC 8/10/13/16; counts; CI corpus+monitor tests"
```

---

## Done criteria

- Both implementations resolve identical (count, redaction) on the corpus inputs, including space- and hyphen-separated forms (the former GT2 divergence), verified by `refuse-space-separated` / `refuse-hyphen-pill` vectors passing on BOTH impls in CI.
- The marker list exists once (conformance/markers.corpus); membrane.py, monitor.py, and emet.rs all consume it.
- refuse and monitor echo corpus_version + corpus_sha256; a missing corpus is UNVERIFIABLE reason=E_NO_CORPUS, never a silent empty denylist.
- corpus_version is a real, sha-pinned artifact (no longer the bare "0").
- Reference: test_membrane.py 19, test_corpus.py 6, test_monitor.py 2, conformance 14/14. Rust verified by CI.
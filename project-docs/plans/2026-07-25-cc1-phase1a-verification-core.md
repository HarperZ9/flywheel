# CC-1 Phase 1A (Verification Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the criterion object, the first construction-certificate checker with a parameterized generator and an independent reimplementation, and the verifier QA gate that must clear before any verdict is treated as a reward. Plus repair the desktop authentication break Phase 0 created.

**Architecture:** A criterion is a hash-pinned data object, not config: it names the family, the generator and its seed range, the objective mapping, the scope bounds, and the decision rule. A `CertificateOracle` checks a data structure against an exact predicate and never executes candidate code. Each family ships a second, independently implemented checker wired to the existing `RLItem.held_out` slot, so disagreement becomes UNDECIDED rather than a coin flip. `oracle_qa` attacks every checker with planted exploits and near-miss mutants before the registry will admit it, and reports a false-accept rate as a Wilson upper bound rather than a zero-count boolean.

**Tech Stack:** Python 3.10+ stdlib only for everything under `harness/` (the offline verifier promise, enforced by `scripts/check_verifier_stdlib.py`). `fractions.Fraction` for exact arithmetic. Dart/Flutter for Task 1 only. pytest.

## Global Constraints

Copied verbatim from `project-docs/specs/2026-07-25-certified-commons-design.md`:

- No receipt, no accept. No learned model on the accept path; an external oracle disposes.
- Verdicts are PASS, FAIL, UNDECIDED, UNVERIFIABLE. UNVERIFIABLE is first-class and **must say why** (spec section 3a item 4).
- A criterion carries a **domain of applicability**. Verification machinery is fenced out of aesthetic and interpretive domains. A poem has no kernel.
- Criterion edits after a miss are recorded events, never quiet retcons.
- Records are append-only: repair adds on top, never rewrites.
- Receipts state what they do NOT prove.
- Consensus is never a verifier: votes propose, proofs dispose. A non-conjunctive decision rule is refused reward eligibility at registry admission.
- Verifier QA **precedes** training. No QA card, no reward eligibility.
- `harness/` is stdlib-only. Files stay under 300 lines; the burn-down list in `records/2026-07-25-file-gate-burndown.md` may only shrink.
- No aggregate is ever computed over the person. No trust score, ever.
- Voice rule for all prose: no em-dashes.
- Apache-2.0 for everything load-bearing for verification.

**Verified repository facts this plan depends on** (re-read at HEAD `3c7fb6d`, branch `feat/cc1-phase0-ground`):

- `harness/verdict.py` defines `Verdict`, `Execution`, `Attribution`, `UndecidedReason`, `UnverifiableReason`, `is_dispositive`, `attribution_for`.
- `harness/oracle.py` `OracleResult.__init__(cmd, output_hash, stdout_excerpt, rc, passed=None, verdict_=None, execution=..., attribution=None, raw_stdout_sha256="", duration_ns=0, objective=None)`; `passed` is a property raising `NonDispositiveVerdict`; `Oracle` Protocol requires `oracle_type: str` and `verify(candidate, task) -> OracleResult`.
- `harness/rl_from_oracle.py` `RLItem(task, oracle, held_out=None)`; `RLFromOracle(proposer, *, group_size=8, temperature=1.0, estimator="drgrpo", max_new_tokens=None, seed_origin=0)`.
- `harness/matmul_oracle.py` `verify_scheme(scheme) -> (bool, str)`, `MatMulSchemeOracle`, `naive_scheme`, `strassen_scheme`, `perturb_scheme`, `drop_triple`, `dumps`.
- `harness/task_curator.py` exists and holds the admission gates for the hard-set lane.
- `C:\dev\flywheel-desktop` `lib/client/gateway_client.dart` has 40 `_http.get`/`_http.post` call sites; `lib/client/gateway_streams.dart` builds 2 `http.Request` objects and calls `_http.send`. All traffic passes through the single `_http` field, so one authenticating `http.BaseClient` covers every call site.
- `harness/gateway_auth.py` writes the token to `FLYWHEEL_HOME/gateway.token`, default `~/.flywheel`.

---

### Task 1: Repair the desktop authentication break

**Files:**
- Create: `C:\dev\flywheel-desktop\lib\client\auth_client.dart`
- Modify: `C:\dev\flywheel-desktop\lib\client\gateway_client.dart` (constructor only)
- Test: `C:\dev\flywheel-desktop\test\auth_client_test.dart`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces: `AuthClient extends http.BaseClient` with `AuthClient(http.Client inner, String? token)`; `String? readGatewayToken({String? homeOverride})`

**Why:** Phase 0 Task 7 added gateway authentication and did not update the gateway's main consumer, so the desktop app now receives 401 on every route. This is a regression this program created and it is repaired first. One `BaseClient` wrapper injects the header for all 42 call sites including the two SSE streams, because every request goes through the single `_http` field.

- [ ] **Step 1: Write the failing test**

Create `test/auth_client_test.dart`:

```dart
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:flywheel_desktop/client/auth_client.dart';

class _Recorder extends http.BaseClient {
  final List<Map<String, String>> seen = [];
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    seen.add(Map<String, String>.from(request.headers));
    return http.StreamedResponse(
        Stream.value(utf8.encode('{"ok":true}')), 200);
  }
}

void main() {
  test('a token is sent as a bearer header on every request', () async {
    final rec = _Recorder();
    final client = AuthClient(rec, 'tok-abc');
    await client.get(Uri.parse('http://127.0.0.1:8799/api/world'));
    await client.post(Uri.parse('http://127.0.0.1:8799/api/companion'),
        headers: {'Content-Type': 'application/json'}, body: '{}');
    expect(rec.seen.length, 2);
    for (final h in rec.seen) {
      expect(h['authorization'] ?? h['Authorization'], 'Bearer tok-abc');
    }
  });

  test('a null token sends no authorization header at all', () async {
    final rec = _Recorder();
    await AuthClient(rec, null).get(Uri.parse('http://127.0.0.1:8799/api/world'));
    final h = rec.seen.single;
    expect(h.containsKey('authorization') || h.containsKey('Authorization'),
        isFalse);
  });

  test('an existing content type is preserved', () async {
    final rec = _Recorder();
    await AuthClient(rec, 'tok').post(
        Uri.parse('http://127.0.0.1:8799/api/companion'),
        headers: {'Content-Type': 'application/json'}, body: '{}');
    expect(rec.seen.single['content-type'], contains('application/json'));
  });

  test('a missing token file yields null rather than throwing', () {
    expect(readGatewayToken(homeOverride: '/definitely/not/a/real/path'), isNull);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/flutter/bin/flutter test test/auth_client_test.dart`
Expected: FAIL, `Error: Couldn't resolve the package 'flywheel_desktop'` or `auth_client.dart` not found.

- [ ] **Step 3: Write minimal implementation**

Create `lib/client/auth_client.dart`:

```dart
// auth_client.dart: attach the gateway bearer token to every request.
//
// The gateway requires a bearer token, a loopback Host, and a JSON content type
// on state-changing methods. Rather than edit 42 call sites, this wraps the
// inner http.Client: every request the typed client makes, including the two SSE
// streams, passes through send() here.
//
// The token is a local file the gateway wrote at 0600. This app never displays
// it, never logs it, and never puts it in a URL.

import 'dart:io';

import 'package:http/http.dart' as http;

const String tokenFilename = 'gateway.token';

/// Read the gateway token from FLYWHEEL_HOME (default ~/.flywheel).
/// Returns null when the file is absent or unreadable: an unauthenticated
/// client is a legitimate state (an older gateway does not require a token),
/// and a missing file must degrade rather than crash the app.
String? readGatewayToken({String? homeOverride}) {
  try {
    final home = homeOverride ??
        Platform.environment['FLYWHEEL_HOME'] ??
        '${Platform.environment['USERPROFILE'] ?? Platform.environment['HOME']}'
            '${Platform.pathSeparator}.flywheel';
    final f = File('$home${Platform.pathSeparator}$tokenFilename');
    if (!f.existsSync()) return null;
    final t = f.readAsStringSync().trim();
    return t.isEmpty ? null : t;
  } catch (_) {
    return null;
  }
}

class AuthClient extends http.BaseClient {
  final http.Client _inner;
  final String? _token;

  AuthClient(this._inner, this._token);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    final t = _token;
    if (t != null) request.headers['Authorization'] = 'Bearer $t';
    return _inner.send(request);
  }

  @override
  void close() => _inner.close();
}
```

- [ ] **Step 4: Wire it into the typed client**

In `lib/client/gateway_client.dart`, add the import after the existing `http` import:

```dart
import 'auth_client.dart';
```

and replace the constructor:

```dart
  GatewayClient({this.baseUrl = 'http://127.0.0.1:8799', http.Client? httpClient})
      : _http = httpClient ?? AuthClient(http.Client(), readGatewayToken());
```

Passing an explicit `httpClient` still bypasses auth, which is what the existing widget tests rely on.

- [ ] **Step 5: Run the tests**

Run: `C:/flutter/bin/flutter test`
Expected: the 4 new tests pass and the existing 124 still pass.

Then: `C:/flutter/bin/flutter analyze`
Expected: `No issues found!`

- [ ] **Step 6: Commit**

```bash
git add lib/client/auth_client.dart lib/client/gateway_client.dart test/auth_client_test.dart
git commit -m "fix(client): send the gateway bearer token on every request"
```

---

### Task 2: The criterion object

**Files:**
- Create: `harness/criteria/__init__.py`
- Create: `harness/criteria/spec.py`
- Test: `tests/test_criterion_spec.py`

**Interfaces:**
- Consumes: `harness.verdict.Verdict`
- Produces: `Criterion` dataclass; `DecisionRule` str enum (`CONJUNCTIVE`, `DISJUNCTIVE`, `MAJORITY`, `WEIGHTED`); `Domain` str enum (`CONSTRUCTIVE`, `FORMAL`, `COMPUTATIONAL`, `EMPIRICAL`, `INTERPRETIVE`); `Criterion.sha256() -> str`; `Criterion.amend(reason, **changes) -> Criterion`; `Criterion.reward_eligible() -> tuple[bool, str]`; `CriterionError`

**Why:** a criterion that lives in config is a criterion that can be edited after a miss without anyone noticing. Making it a hash-pinned object with an explicit `amend` that records `change_reason` and `parent_sha256` turns a quiet retcon into an append-only event. The `domain` field is the fence from spec section 3a item 6: an interpretive domain is never reward-eligible.

- [ ] **Step 1: Write the failing test**

Create `tests/test_criterion_spec.py`:

```python
import pytest

from harness.criteria.spec import (
    Criterion, DecisionRule, Domain, CriterionError,
)


def _c(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2",
        version=1,
        family="zarankiewicz",
        generator_id="zarankiewicz.bipartite.v1",
        generator_version=1,
        seed_range=(0, 1024),
        objective_direction="maximize",
        objective_normalization="ratio_to_incumbent",
        reward_mapping={"valid_gate": True, "scale": "linear"},
        incumbent_source="operator_search",
        scope_bounds={"m_max": 40, "n_max": 40},
        decision_rule=DecisionRule.CONJUNCTIVE,
        domain=Domain.CONSTRUCTIVE,
        license_id="Apache-2.0",
    )
    base.update(kw)
    return Criterion(**base)


def test_sha256_is_stable_and_full_length():
    a, b = _c(), _c()
    assert a.sha256() == b.sha256()
    assert a.sha256().startswith("sha256:")
    assert len(a.sha256().split(":", 1)[1]) == 64


def test_any_field_change_changes_the_hash():
    base = _c().sha256()
    assert _c(version=2).sha256() != base
    assert _c(seed_range=(0, 2048)).sha256() != base
    assert _c(scope_bounds={"m_max": 41, "n_max": 40}).sha256() != base


def test_amend_records_its_parent_and_reason_and_bumps_the_version():
    a = _c()
    b = a.amend("incumbent table was revised", scope_bounds={"m_max": 50, "n_max": 50})
    assert b.parent_sha256 == a.sha256()
    assert b.change_reason == "incumbent table was revised"
    assert b.version == a.version + 1
    assert b.sha256() != a.sha256()


def test_amend_without_a_reason_is_refused():
    with pytest.raises(CriterionError):
        _c().amend("", scope_bounds={"m_max": 50})


def test_amend_cannot_silently_change_the_family():
    with pytest.raises(CriterionError):
        _c().amend("sneaky", family="something_else")


def test_conjunctive_rules_are_reward_eligible():
    ok, reason = _c(decision_rule=DecisionRule.CONJUNCTIVE).reward_eligible()
    assert ok is True
    assert reason == "ok"


def test_non_conjunctive_rules_are_refused_reward_eligibility():
    for rule in (DecisionRule.DISJUNCTIVE, DecisionRule.MAJORITY,
                 DecisionRule.WEIGHTED):
        ok, reason = _c(decision_rule=rule).reward_eligible()
        assert ok is False, rule
        assert reason == "NON_CONJUNCTIVE_RULE"


def test_an_interpretive_domain_is_never_reward_eligible():
    # A poem has no kernel. The fence lives in the criterion, not in a reviewer.
    ok, reason = _c(domain=Domain.INTERPRETIVE).reward_eligible()
    assert ok is False
    assert reason == "INTERPRETIVE_DOMAIN"


def test_an_empty_seed_range_is_refused_at_construction():
    with pytest.raises(CriterionError):
        _c(seed_range=(100, 100))


def test_a_backwards_seed_range_is_refused():
    with pytest.raises(CriterionError):
        _c(seed_range=(100, 10))


def test_to_dict_roundtrips_through_from_dict():
    a = _c()
    assert Criterion.from_dict(a.to_dict()).sha256() == a.sha256()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_criterion_spec.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'harness.criteria'`

- [ ] **Step 3: Write minimal implementation**

Create `harness/criteria/__init__.py`:

```python
"""criteria -- the criterion object and its registry.

A criterion is data, hash-pinned and forkable, never runtime config. Editing one
after a miss is an append-only event with a recorded reason, not a quiet retcon.
"""
from .spec import Criterion, DecisionRule, Domain, CriterionError  # noqa: F401
```

Create `harness/criteria/spec.py`:

```python
"""spec.py -- the criterion: what would count, decided before the attempt.

The robe the essay names is a judge who writes the criterion, profits from the
verdict, and blocks re-checking. The mechanical answer is that a criterion is a
hash-pinned object a third party can read and fork, that an edit after a miss
records its parent and its reason, and that certain shapes are refused reward
eligibility outright:

  - a non-conjunctive decision rule, because votes propose and proofs dispose,
  - an interpretive domain, because a poem has no kernel.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, replace, field
from enum import Enum


class CriterionError(ValueError):
    """A criterion that cannot be trusted to mean the same thing twice."""


class DecisionRule(str, Enum):
    CONJUNCTIVE = "CONJUNCTIVE"      # every check must pass
    DISJUNCTIVE = "DISJUNCTIVE"      # any check passing suffices
    MAJORITY = "MAJORITY"            # a vote
    WEIGHTED = "WEIGHTED"            # a weighted vote


class Domain(str, Enum):
    CONSTRUCTIVE = "CONSTRUCTIVE"    # a certificate a checker validates
    FORMAL = "FORMAL"                # a proof a kernel validates
    COMPUTATIONAL = "COMPUTATIONAL"  # an execution test
    EMPIRICAL = "EMPIRICAL"          # a measurement
    INTERPRETIVE = "INTERPRETIVE"    # aesthetic or interpretive: NEVER rewarded


REWARD_ELIGIBLE_DOMAINS = frozenset({
    Domain.CONSTRUCTIVE, Domain.FORMAL, Domain.COMPUTATIONAL,
})

# Fields an amendment may never touch: changing them makes it a different
# criterion wearing the same name.
IMMUTABLE_ON_AMEND = ("criterion_id", "family")


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    version: int
    family: str
    generator_id: str
    generator_version: int
    seed_range: tuple[int, int]
    objective_direction: str
    objective_normalization: str
    reward_mapping: dict
    incumbent_source: str
    scope_bounds: dict
    decision_rule: DecisionRule
    domain: Domain
    license_id: str
    parent_sha256: str = ""
    change_reason: str = ""

    def __post_init__(self) -> None:
        lo, hi = self.seed_range
        if hi <= lo:
            raise CriterionError(
                f"seed_range must be a non-empty ascending half-open interval, "
                f"got {self.seed_range}")
        if self.objective_direction not in ("maximize", "minimize"):
            raise CriterionError(
                f"objective_direction must be maximize or minimize, "
                f"got {self.objective_direction!r}")
        if not self.criterion_id or not self.family:
            raise CriterionError("criterion_id and family are required")

    def _preimage(self) -> str:
        d = asdict(self)
        d["seed_range"] = list(self.seed_range)
        d["decision_rule"] = self.decision_rule.value
        d["domain"] = self.domain.value
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self._preimage().encode()).hexdigest()

    def amend(self, reason: str, **changes) -> Criterion:
        """Produce the successor criterion. Append-only: the parent hash and the
        reason ride along, so an edit after a miss is visible as an edit."""
        if not reason.strip():
            raise CriterionError("an amendment must record why")
        for k in IMMUTABLE_ON_AMEND:
            if k in changes and changes[k] != getattr(self, k):
                raise CriterionError(f"{k} cannot change in an amendment")
        return replace(self, version=self.version + 1,
                       parent_sha256=self.sha256(), change_reason=reason,
                       **changes)

    def reward_eligible(self) -> tuple[bool, str]:
        """Whether a verdict under this criterion may become a training reward."""
        if self.domain not in REWARD_ELIGIBLE_DOMAINS:
            return False, "INTERPRETIVE_DOMAIN"
        if self.decision_rule is not DecisionRule.CONJUNCTIVE:
            return False, "NON_CONJUNCTIVE_RULE"
        return True, "ok"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["seed_range"] = list(self.seed_range)
        d["decision_rule"] = self.decision_rule.value
        d["domain"] = self.domain.value
        d["criterion_sha256"] = self.sha256()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Criterion:
        d = dict(d)
        d.pop("criterion_sha256", None)
        d["seed_range"] = tuple(d["seed_range"])
        d["decision_rule"] = DecisionRule(d["decision_rule"])
        d["domain"] = Domain(d["domain"])
        return cls(**d)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_criterion_spec.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Confirm the verifier stays stdlib-only and under the gate**

Run: `python scripts/check_verifier_stdlib.py && python scripts/check_file_gate.py`
Expected: both clean. `spec.py` must be under 300 lines; it is roughly 150.

- [ ] **Step 6: Commit**

```bash
git add harness/criteria/__init__.py harness/criteria/spec.py tests/test_criterion_spec.py
git commit -m "feat(criteria): the criterion object, hash-pinned with recorded amendments"
```

---

### Remaining Phase 1A tasks

Tasks 3 through 7 are specified in the spec's Layer 1 and are written out when Task 2 lands, so that the interfaces they consume are real rather than predicted. Each keeps the same shape: failing test, verify the failure, minimal implementation, verify the pass, gate checks, commit.

- **Task 3: criterion registry** (`harness/criteria/registry.py`). Versioned incumbent reference set as plain JSON so a fork edits data and not Python. Admission refuses any criterion whose `reward_eligible()` is False. Named invalidation codes. Requires two independent citations for a published incumbent, or the mark `operator_search`.
- **Task 4: `CertificateOracle` base** (`harness/certificates/base.py`). Pure data checking, exact integer arithmetic, never executes candidate code. Rejects out-of-envelope declared parameters before dispatch. Emits a `coverage` block: predicate exact or bounded, enumerated fraction, stop reason, the parameter above which the guarantee weakens.
- **Task 5: Zarankiewicz checker and generator** (`harness/certificates/zarankiewicz.py`, `harness/certificates/generators.py`). K_{s,t}-free bipartite witness validation by bitset scan. The generator takes a difficulty knob and produces instances in parameter space absent from published tables, which is what makes the memorization control arm meaningful later.
- **Task 6: independent reimplementation** (`harness/certificates/independent.py`). A second checker for the same predicate by a different algorithm, wired to `RLItem.held_out`. Disagreement yields UNDECIDED with `UndecidedReason.HELD_OUT_DISAGREEMENT`, never the majority side. Includes spec-level mutation testing over the encoding grammar, because two implementations of one spec share spec-level exploits.
- **Task 7: verifier QA** (`harness/oracle_qa.py`). Known-valid generators, near-miss mutants, and planted detectable exploits: duplicate edges, out-of-range indices, declared-versus-actual mismatch, homoglyph separators, trailing garbage, adversarial size and nesting. Reports false-accept rate as a **Wilson upper bound at a declared confidence with a required n per mutation class**, never a zero-count boolean. Emits an `OracleQACard`; absent card means not reward-eligible, enforced at registry admission.

## Self-Review

**Spec coverage.** Phase 1A covers spec Layer 1 (criteria and checkers) plus the desktop authentication repair recorded as a known break in the Phase 0 acceptance record. It does NOT cover Layer 2 (receipts, signing, ledger, bundle, contest), Layer 5 (the science), Layer 6 (training), or the desktop receipt renderer. Those are Phase 1B and 1C and get their own plans, because each produces working testable software on its own and bundling them would produce a plan nobody could review.

**Placeholder scan.** Tasks 1 and 2 contain complete code and exact commands. Tasks 3 through 7 are deliberately specified rather than fully written, and that is stated plainly above rather than disguised as detail: writing their code now would mean predicting interfaces that Task 2 has not yet fixed. This is a scoping decision, not a TODO.

**Type consistency.** `Criterion`, `DecisionRule`, `Domain`, `CriterionError` are defined in Task 2 and named identically in the Task 3 description. `RLItem.held_out` in Task 6 matches the verified signature. `UndecidedReason.HELD_OUT_DISAGREEMENT` in Task 6 exists in `harness/verdict.py` as of Phase 0.

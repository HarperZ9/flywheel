"""The injection-robustness probe measures the gate's containment, and it can fail.

Under the safe default (writes and exec off), every injection in the fixed corpus is
contained: a smuggled write/edit is refused by the gate and a workspace escape by the
path guard. When exec is granted, the probe honestly reports that exec-smuggled
actions are no longer contained (an open shell is a superset capability), so the
measurement is real, not decorative. The receipt re-derives from the same corpus.
"""

from relay.injection_probe import probe, SCENARIOS, _receipt


def _noop_runner(cmd, root):
    return True, "[probe: not executed]"


def test_default_gate_contains_every_injection():
    out = probe(runner=_noop_runner)
    assert out["schema"] == "relay.injection-robustness/v1"
    assert out["contained"] == out["total"] == len(SCENARIOS)
    assert all(r["contained"] for r in out["results"])


def test_granting_exec_removes_containment_for_exec_smuggled_actions():
    out = probe(allow_exec=True, runner=_noop_runner)
    # the probe is a real measurement: with exec on, at least one exec scenario is NOT contained
    exec_results = [r for r in out["results"] if r["forbidden"].startswith("exec")]
    assert exec_results and any(not r["contained"] for r in exec_results)
    # ...but workspace escapes are still contained by the path guard, exec or not
    escapes = [r for r in out["results"] if r["forbidden"] == "workspace-escape"]
    assert escapes and all(r["contained"] for r in escapes)


def test_the_receipt_re_derives_from_the_same_corpus():
    out = probe(runner=_noop_runner)
    again = probe(runner=_noop_runner)
    assert out["receipt"] == again["receipt"]
    # a receipt binds the results body; a tampered body would not re-derive
    assert _receipt(out["results"], out["gate"]) == out["receipt"]


def test_probe_never_touches_the_working_tree(tmp_path, monkeypatch):
    # even granting write and exec, the probe must not create the tamper targets in cwd:
    # it measures the gate inside a disposable sandbox that is removed afterwards.
    monkeypatch.chdir(tmp_path)
    probe(allow_write=True, allow_exec=True, runner=_noop_runner)
    assert not (tmp_path / "auth.py").exists()
    assert not (tmp_path / "tests" / "test_core.py").exists()
    assert not (tmp_path / "conftest.py").exists()
    assert not any(tmp_path.iterdir())          # the sandbox lives and dies elsewhere


def test_every_scenario_is_inspectable_data_not_a_generated_attack():
    # the corpus is fixed and readable: each scenario names its injected text and the exact
    # tool call it smuggles, so a reviewer can audit what the probe tests.
    for s in SCENARIOS:
        assert s["id"] and s["injected"] and s["smuggled"] and s["forbidden"]
        name, args = s["smuggled"]
        assert isinstance(name, str) and isinstance(args, dict)

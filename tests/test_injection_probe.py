"""The engine's defensive prompt-injection robustness probe must:
(1) contain every smuggled tool call under the safe default gate;
(2) honestly open exactly the capability a granted flag confers -- exec opens the
    shell scenarios, write opens the write scenarios, and in THIS engine the two
    gates are INDEPENDENT (granting one does not grant the other);
(3) keep workspace confinement holding even when both flags are granted;
(4) carry a receipt that is reproducible for a gate posture and changes when the
    posture changes;
(5) never touch the live tree -- it measures the gate in a disposable sandbox and
    generates no attacks (the scenario corpus is fixed, inspectable data)."""

from harness.injection_probe import SCENARIOS, probe


def _by_id(report):
    return {r["id"]: r for r in report["results"]}


def test_safe_default_contains_every_scenario():
    report = probe()
    assert report["total"] == len(SCENARIOS)
    assert report["contained"] == report["total"]
    assert all(r["contained"] for r in report["results"])


def test_granting_exec_opens_only_the_shell_scenarios():
    r = _by_id(probe(allow_exec=True))
    assert r["exec-exfiltrate"]["contained"] is False
    assert r["exec-redirect-write"]["contained"] is False
    # the write gate is independent: exec does not open writes in this engine
    assert r["write-test-tamper"]["contained"] is True
    assert r["edit-remove-auth"]["contained"] is True
    assert r["patch-smuggle"]["contained"] is True


def test_granting_write_opens_only_the_write_scenarios():
    r = _by_id(probe(allow_write=True))
    assert r["write-test-tamper"]["contained"] is False
    assert r["edit-remove-auth"]["contained"] is False
    assert r["patch-smuggle"]["contained"] is False
    # the exec gate is independent: write does not open the shell
    assert r["exec-exfiltrate"]["contained"] is True
    assert r["exec-redirect-write"]["contained"] is True


def test_workspace_confinement_holds_even_when_both_flags_granted():
    r = _by_id(probe(allow_write=True, allow_exec=True))
    for esc in ("read-escape-secrets", "list-escape-root", "grep-escape-tree"):
        assert r[esc]["contained"] is True, esc


def test_receipt_is_reproducible_and_posture_sensitive():
    a, b = probe(), probe()
    assert a["receipt"] == b["receipt"]
    assert probe(allow_exec=True)["receipt"] != a["receipt"]
    assert probe(allow_write=True)["receipt"] != a["receipt"]


def test_probe_never_writes_to_the_live_tree(tmp_path, monkeypatch):
    # even granting write, the tamper targets must not appear in the working tree
    monkeypatch.chdir(tmp_path)
    probe(allow_write=True, allow_exec=True)
    assert not (tmp_path / "tests" / "test_core.py").exists()
    assert not (tmp_path / "auth.py").exists()
    assert not any(tmp_path.iterdir())          # the sandbox is disposed elsewhere


def test_corpus_is_static_inspectable_data():
    # nothing is generated: every scenario is a plain dict a reviewer can audit
    assert len(SCENARIOS) >= 6
    for s in SCENARIOS:
        assert set(s) >= {"id", "forbidden", "injected", "smuggled"}
        assert isinstance(s["smuggled"], tuple) and len(s["smuggled"]) == 2

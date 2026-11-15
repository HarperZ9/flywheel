"""A plexus plan is a claim: 'given THESE manifests, this is the wiring.' The receipt
binds the derivation to the exact manifests, so a stranger re-derives the identical
plan or rejects it, and a manifest that changed since the plan is caught as drift --
the wiring silently shifting under you is the failure this prevents."""

from plexus.manifest import Manifest, Port
from plexus.mesh import discover
from plexus.plan import plan_to, route
from plexus.receipt import METHOD_VERSION, build_plan_receipt, verify_plan


def _m(organ, emits=(), consumes=()):
    return Manifest(organ=organ, invoke={"cli": organ},
                    emits=[Port(*e) for e in emits], consumes=[Port(*c) for c in consumes])


A = _m("a", emits=[("x/1",)])
B = _m("b", emits=[("y/1",)], consumes=[("x/1",)])
C = _m("c", consumes=[("y/1",)])


def test_plan_carries_a_receipt_binding_every_organ():
    plan = plan_to(discover([A, B, C]), "c")
    r = plan["receipt"]
    assert r["schema"] == "plexus.plan-receipt/1" and r["method_version"] == METHOD_VERSION
    assert set(r["manifest_shas"]) == {"a", "b", "c"}
    assert len(r["plan_sha256"]) == 64


def test_an_intact_plan_verifies():
    mesh = discover([A, B, C])
    assert verify_plan(plan_to(mesh, "c"), mesh) is True


def test_a_tampered_plan_fails_even_when_the_receipt_hash_is_recomputed():
    mesh = discover([A, B, C])
    plan = plan_to(mesh, "c")
    plan["order"] = ["c", "b", "a"]                    # lie about the dependency order
    plan["receipt"] = build_plan_receipt(mesh, plan)  # a forger recomputes the hash to match
    # verify re-derives from the mesh, so the fabricated body is caught anyway
    assert verify_plan(plan, mesh) is False


def test_a_changed_manifest_makes_the_wiring_drift_visible():
    plan = plan_to(discover([A, B, C]), "c")
    # the toolchain changed under us: b now emits a different capability, so b no
    # longer feeds c. the old plan must not verify against the new mesh.
    B2 = _m("b", emits=[("y2/1",)], consumes=[("x/1",)])
    assert verify_plan(plan, discover([A, B2, C])) is False


def test_route_also_carries_a_verifiable_receipt():
    mesh = discover([A, B, C])
    r = route(mesh, "a", "c")
    assert r["receipt"]["method_version"] == METHOD_VERSION
    assert verify_plan(r, mesh) is True


def test_cli_verify_re_derives_a_saved_plan(tmp_path, capsys):
    import json

    from plexus import cli
    assert cli.main(["plan", "--goal", "crucible", "--builtin"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert "receipt" in plan
    pf = tmp_path / "plan.json"
    pf.write_text(json.dumps(plan), encoding="utf-8")
    assert cli.main(["verify", "--plan", str(pf), "--builtin"]) == 0   # re-derives, exit 0
    out = json.loads(capsys.readouterr().out)
    assert out["verified"] is True and out["target"] == "crucible"

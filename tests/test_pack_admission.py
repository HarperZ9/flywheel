"""Pack admission: verify, persist, and fire the pack.admitted hook.

Admission is where two pillars interlock -- a domain pack becomes
run-root state AND an accountable-hooks event, so a failing blocking
hook marks the admission blocked like every other event on this
platform. Admitted manifests are immutable: a different pack_sha256
under the same pack_id refuses rather than overwrites."""
import json
from pathlib import Path

import pytest

from harness import pack_admission
from harness.accountable_hooks import register_hook, save_registry
from harness.pack_admission import admit_pack, list_admitted

REPO_PACKS = Path(__file__).resolve().parents[1] / "packs"


def _blocking_hook(tmp_path):
    reg = register_hook(event="pack.admitted",
                        argv=["python", "-c", "import sys; sys.exit(5)"],
                        blocking=True, hook_id="hook_" + "f" * 8,
                        created_at="2026-08-25T00:00:00Z")
    save_registry([reg], registry_path=tmp_path / "hooks" / "registry.json")


def _admit(domain, run_root, clock=lambda: "t"):
    return admit_pack(
        manifest=json.loads(
            (REPO_PACKS / domain / "domain-pack.json").read_text(
                encoding="utf-8")),
        fixtures_root=REPO_PACKS / domain,
        run_root=run_root, clock=clock)


def test_admission_persists_and_fires_the_hook_with_teeth(tmp_path):
    _blocking_hook(tmp_path)
    ack = _admit("medicine-terminology", tmp_path)
    assert ack["schema"] == "flywheel.domain-pack-admission/v1"
    assert ack["event_blocked"] is True
    assert ack["hook_receipts"][0]["exit_code"] == 5
    persisted = json.loads((tmp_path / "packs" /
                            "flywheel.medicine.terminology" /
                            "manifest.json").read_text(encoding="utf-8"))
    assert persisted["pack_sha256"] == ack["pack_sha256"]
    assert persisted["state"] == "data_only"


def test_readmission_is_idempotent_but_drift_refuses(tmp_path):
    first = _admit("design-tokens", tmp_path)
    again = _admit("design-tokens", tmp_path)
    assert again["pack_sha256"] == first["pack_sha256"]
    drifted = json.loads(
        (REPO_PACKS / "design-tokens" / "domain-pack.json").read_text(
            encoding="utf-8"))
    drifted["version"] = "9.9.9"
    with pytest.raises(ValueError):
        admit_pack(manifest=drifted,
                   fixtures_root=REPO_PACKS / "design-tokens",
                   run_root=tmp_path, clock="t")
    on_disk = json.loads((tmp_path / "packs" / "flywheel.design.tokens" /
                          "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["version"] == "1.0.0"


def test_all_three_first_party_packs_list_after_admission(tmp_path):
    for domain in ("medicine-terminology", "finance-compliance",
                   "design-tokens"):
        _admit(domain, tmp_path)
    rows = list_admitted(tmp_path)
    ids = {r["pack_id"] for r in rows}
    assert ids == {"flywheel.medicine.terminology",
                   "flywheel.finance.claims", "flywheel.design.tokens"}
    assert all(r["state"] == "data_only" for r in rows)


def test_pack_id_traversal_is_refused(tmp_path):
    evil = json.loads((REPO_PACKS / "design-tokens" / "domain-pack.json")
                      .read_text(encoding="utf-8"))
    evil["pack_id"] = "../evil"
    with pytest.raises(ValueError):
        admit_pack(manifest=evil,
                   fixtures_root=REPO_PACKS / "design-tokens",
                   run_root=tmp_path, clock="t")


def test_routes_round_trip_through_the_gateway(tmp_path, monkeypatch):
    import harness.gateway as gateway

    class _H:
        def __init__(self, n):
            self._n = n

        def get(self, k, d=None):
            return self._n if k == "Content-Length" else d

    def _post(path, body):
        raw = json.dumps(body).encode()
        h = gateway._Handler.__new__(gateway._Handler)
        h.path = path
        h.headers = _H(str(len(raw)))
        h.rfile = __import__("io").BytesIO(raw)
        sent = {}
        h._json = lambda b, code=200: sent.update(body=b, code=code)
        h._post()
        return sent

    def _get(path):
        h = gateway._Handler.__new__(gateway._Handler)
        h.path = path
        h.headers = _H("0")
        sent = {}
        h._json = lambda b, code=200: sent.update(body=b, code=code)
        h._get()
        return sent

    for attr, val in (("run_root", str(tmp_path)),
                      ("owner_ref", "owner_" + "a" * 32),
                      ("flywheel_home", tmp_path),
                      ("clock", lambda *a: "2026-08-25T01:00:00Z")):
        monkeypatch.setattr(gateway._Handler, attr, val, raising=False)

    manifest = json.loads(
        (REPO_PACKS / "finance-compliance" / "domain-pack.json")
        .read_text(encoding="utf-8"))
    sent = _post("/api/packs/admit",
                 {"manifest": manifest,
                  "fixtures_root": str(REPO_PACKS / "finance-compliance")})
    assert sent["code"] == 200
    assert sent["body"]["pack_id"] == "flywheel.finance.claims"

    listed = _get("/api/packs")
    assert listed["code"] == 200
    assert listed["body"]["count"] == 1

    assert _post("/api/packs/explode", {})["code"] == 404
    assert _get("/api/packs/nope")["code"] == 404

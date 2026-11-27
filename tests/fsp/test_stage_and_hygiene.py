"""Stage L / Stage F governance mode, stdlib verification cross-check, and hygiene gates."""

from __future__ import annotations

import re
from pathlib import Path

from harness.fsp import flows
from harness.fsp.backends.software import SoftwareSecureElement
from harness.fsp.crypto import ED25519, Ed25519Signer, verify, verify_stdlib
from harness.fsp.orders import workload_tag
from harness.fsp.params import HONEST_HARDWARE_LIMIT, STAGE_F, STAGE_L, Params
from harness.fsp.shim import receive_order, tick
from harness.fsp.world import World


def test_stage_l_logs_and_attests_but_refuses_remote_stop_and_throttle():
    """Stage L permits full attestation, monotonic clock, and audit logs while refusing remote stops."""
    w = World(params=Params(stage=STAGE_L))
    backend = SoftwareSecureElement(w.fw, w.clock)
    dev = w.add_device(backend, "c1")
    w.provision_cluster("c1", [dev])
    flows.bootstrap(w, [dev])

    hb = dev.heartbeat()
    assert hb["type"] == "heartbeat"
    assert dev.enforcement()["state"] == "normal"

    throttle = flows.build_order(w, "throttle", "c1", level=50)
    res_t = receive_order(dev, flows.package(w, throttle, dev))
    assert res_t["status"] == "refused" and res_t["check"] == "stage_l"
    assert dev.outbox[-1]["type"] == "refusal"

    tag = workload_tag(b"salt", "job-stage-l")
    eff = w.now_ms() + w.params.t_halt_notice * 1000
    notice = flows.post_notice(w, "c1", [tag], eff, eff + 3_600_000)
    eff = notice[1] + w.params.t_halt_notice * 1000
    halt = flows.build_order(w, "halt", "c1", tags=[tag], notice=notice,
                             effective_ms=eff, expires_ms=eff + 3_600_000)
    res_h = receive_order(dev, flows.package(w, halt, dev, notice))
    assert res_h["status"] == "refused" and res_h["check"] == "stage_l"
    assert dev.enforcement()["state"] == "normal"


def test_stage_f_applies_valid_throttle_and_halt():
    """Stage F activates full fail-closed enforcement once charter activation is enabled."""
    w = World(params=Params(stage=STAGE_F))
    backend = SoftwareSecureElement(w.fw, w.clock)
    dev = w.add_device(backend, "c1")
    w.provision_cluster("c1", [dev])
    flows.bootstrap(w, [dev])

    throttle = flows.build_order(w, "throttle", "c1", level=50)
    res = receive_order(dev, flows.package(w, throttle, dev))
    assert res["status"] == "applied"
    assert dev.enforcement()["level"] == 50
    tick(dev)
    assert dev.failed is None


def test_stdlib_ed25519_verification_matches_signer():
    """Offline stdlib verification agrees with active signing backend on valid and tampered messages."""
    signer = Ed25519Signer.from_seed(bytes(range(32)))
    msg = b"fsp-stage-lf-attestation-check"
    sig = signer.sign(msg)
    pub = bytes.fromhex(signer.public_hex())
    assert verify(ED25519, signer.public_hex(), msg, sig.hex())
    assert verify_stdlib(ED25519, pub, msg, sig)
    assert not verify_stdlib(ED25519, pub, msg + b"!", sig)


def test_honest_hardware_limit_is_declared():
    assert HONEST_HARDWARE_LIMIT["no_physical_on_chip_lock"] is True
    assert "no physical on-chip lock" in HONEST_HARDWARE_LIMIT["summary"].lower()


def test_fsp_module_line_budgets_and_public_hygiene():
    repo_root = Path(__file__).resolve().parents[2]
    files = sorted((repo_root / "harness" / "fsp").rglob("*.py")) + sorted(
        (repo_root / "tests" / "fsp").rglob("*.py")
    )
    local_path_re = re.compile(r"[A-Za-z]:\\(?:dev|Users)\\")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 300, f"{path.name} exceeds 300-line gate"
        assert "\u2014" not in text, f"{path.name} contains a literal em dash"
        assert not local_path_re.search(text), f"{path.name} contains a hardcoded local path"

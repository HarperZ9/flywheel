"""Cross-platform WindowsTpmBackend tests (live TPM on Windows hosts, honest fallback on CI)."""

from __future__ import annotations

from harness.fsp import flows
from harness.fsp.backends.windows import WindowsTpmBackend
from harness.fsp.crypto import ED25519, P256, verify, verify_stdlib
from harness.fsp.shim import receive_order
from harness.fsp.world import World


def test_tpm_backend_signs_verifiably_and_reports_honest_sources():
    backend = WindowsTpmBackend("fsp-pytest", "cc" * 32)
    try:
        desc = backend.describe()
        key_desc = desc["key"]
        signer = backend.device_signer()
        sig = signer.sign(b"heartbeat")
        assert verify(signer.alg, signer.public_hex(), b"heartbeat", sig.hex())
        assert not verify(signer.alg, signer.public_hex(), b"heartbeaT", sig.hex())
        assert verify_stdlib(signer.alg, bytes.fromhex(signer.public_hex()), b"heartbeat", sig)
        assert not verify_stdlib(signer.alg, bytes.fromhex(signer.public_hex()), b"heartbeaT", sig)

        if key_desc["source"] == "tpm":
            assert signer.alg == P256
            assert key_desc["private_export_attempt"] != "EXPORTED"
            assert key_desc["export_policy"] == 0
        else:
            assert key_desc["source"] == "software"
            assert signer.alg == ED25519

        # Counter, time floor, and tamper stay explicitly software-backed on commodity PCs
        assert desc["counter"]["source"] == "software"
        assert desc["time_floor"]["source"] == "software"
        assert desc["tamper"]["source"] == "software"
    finally:
        backend.close(delete_key=True)


def test_tpm_backend_clock_is_monotonic_within_a_boot():
    backend = WindowsTpmBackend("fsp-pytest-clk", "dd" * 32)
    try:
        a = backend.elapsed_ms()
        b = backend.elapsed_ms()
        assert b >= a
        assert backend.boot_id() == backend.boot_id()
    finally:
        backend.close(delete_key=True)


def test_gpu_telemetry_is_banded_or_absent():
    backend = WindowsTpmBackend("fsp-pytest-gpu", "ee" * 32)
    try:
        reading = backend.telemetry()
        if reading is not None:
            assert set(reading) == {
                "power_band_w", "power_band_width_w", "util_band_pct", "util_band_width_pct",
            }
            assert reading["power_band_w"] % 50 == 0 and reading["util_band_pct"] % 25 == 0
        else:
            assert backend.describe()["telemetry"]["source"] == "none"
    finally:
        backend.close(delete_key=True)


def test_device_on_tpm_backend_runs_full_protocol():
    w = World()
    backend = WindowsTpmBackend("fsp-pytest-dev", w.fw)
    try:
        dev = w.add_device(backend, "c1")
        w.provision_cluster("c1", [dev])
        flows.bootstrap(w, [dev])
        order = flows.build_order(w, "throttle", "c1", level=50)
        assert receive_order(dev, flows.package(w, order, dev))["status"] == "applied"
        assert dev.outbox[-1]["sigs"][0]["alg"] == backend.device_signer().alg
    finally:
        backend.close(delete_key=True)

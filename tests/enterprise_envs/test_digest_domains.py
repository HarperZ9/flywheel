import hashlib
import json


def test_toy_digest_preimages_are_domain_separated_and_noncircular():
    """Catches digest implementations that hash snapshot/log state into per-event state."""
    from tests.enterprise_envs.package_helpers import add_product_src

    add_product_src()
    from harness.enterprise_envs.digest import canonical_json, digest
    from service_desk_incident_env.v1.toy_digest import toy_digest_example

    example = toy_digest_example()
    before_preimage = example["preimages"]["domain_before"]
    event_preimage = example["preimages"]["action_event"]
    snapshot_preimage = example["preimages"]["snapshot"]

    assert before_preimage.startswith("flywheel.enterprise-env.domain-state/v1\n")
    assert event_preimage.startswith("flywheel.enterprise-env.action-event/v1\n")
    assert snapshot_preimage.startswith("flywheel.enterprise-env.snapshot/v1\n")
    assert "action_log_sha256" not in before_preimage
    assert "snapshot_sha256" not in event_preimage
    assert example["domain_before_sha256"] == "8552cd932a98b4cc7853245c4f2e98ddd0c4118a7bd99547be3e0d1cc559e602"
    assert example["domain_after_sha256"] == "3fcc1d4c780608f501326082791b4f1b9ee5553e974aa4de0fd50f233ceb3765"
    assert example["action_event_sha256"] == "c7bcbdd948c75a0b7b2bbe3981f3d282b0b2c281e8cac750753cabddfdd2786e"
    assert example["action_log_sha256"] == "13a50e562179cf6e383f9b75ec0dcdc96836a1f3a288b1d1aed435ec6c2adf20"
    assert example["snapshot_sha256"] == "fe72b2d4a0f6916744a8491912ed920f7b48c8ddda08137c611ead68d81416a1"

    value = {"b": 2, "a": 1}
    expected = hashlib.sha256(b"domain\n{\"a\":1,\"b\":2}").hexdigest()
    assert canonical_json(value) == '{"a":1,"b":2}'
    assert digest("domain", value) == expected


def test_digest_rejects_nonfinite_values():
    """Catches silent JSON encoders that allow NaN into receipts."""
    from harness.enterprise_envs.digest import canonical_json

    try:
        canonical_json({"value": float("nan")})
    except ValueError:
        return
    raise AssertionError("nonfinite receipt value was accepted")

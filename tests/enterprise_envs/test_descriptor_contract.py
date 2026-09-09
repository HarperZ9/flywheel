from pathlib import Path


def test_service_desk_descriptor_has_artifact_backed_source_basis():
    """Catches source-basis rows that keep only URL labels."""
    from tests.enterprise_envs.package_helpers import add_product_src

    add_product_src()
    from harness.enterprise_envs.descriptors import validate_descriptor
    from service_desk_incident_env.v1.descriptor import descriptor

    doc = descriptor()
    validate_descriptor(doc)

    assert doc["environment_id"] == "service-desk-incident/v1"
    assert doc["authority"]["hidden_control_required"] is True
    assert doc["authority"]["separate_ports_required"] is True
    for row in doc["source_basis"]:
        assert row["source_artifact_ref"]
        assert row["source_manifest_sha256"]
        assert row["source_sha256"]
        assert row["retrieved_at_utc"].endswith("Z")
        assert row["used_for"]


def test_artifact_root_preflight_rejects_source_tree_output():
    """Catches env commands that let DBs and receipts land inside the source checkout."""
    from harness.enterprise_envs.receipts import prepare_artifact_root

    source = Path(__file__).resolve().parents[2]
    result = prepare_artifact_root(source, source / "artifacts", "service-desk-incident/v1")
    assert result["verdict"] == "reject"
    assert result["failure_code"] in {"artifact_root_inside_source", "artifact_root_rejected"}

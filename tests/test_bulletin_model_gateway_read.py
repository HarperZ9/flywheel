"""Native-client envelope regression found by the combined Bulletin fixture."""
from gateway_grant_relay_source_fixture import relay_source_runtime  # noqa: F401

from tests.test_gateway_grant_inbox import _journey, _prepare, _read


def test_read_envelope_keeps_read_schema_instead_of_list_item_schema(tmp_path, relay_source_runtime):
    _journey(tmp_path)
    prepared, status = _prepare(tmp_path)
    assert status == 200
    response, status = _read(tmp_path, prepared)
    assert status == 200
    assert response["review_available"] is True
    assert response["schema"] == "flywheel.gateway-grant-read/v1"
    assert response["review"]["schema"] == "flywheel.gateway-grant-review/v1"

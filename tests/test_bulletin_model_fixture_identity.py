"""The expected actor identity is fixed from setup, never inferred from a reply."""
import importlib.util
from pathlib import Path

from harness.bulletin_identity_key import parse_identity_json
from tests.bulletin_media_fixtures import jwk_json


def test_fixture_thumbprint_matches_existing_signer_without_private_output():
    path = Path(__file__).resolve().parents[1] / "desktop/tool/bulletin_media_gateway_fixture.py"
    spec = importlib.util.spec_from_file_location("fixture_identity_control", path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    first, public = jwk_json()
    second, another = jwk_json()
    expected = parse_identity_json(first).thumbprint
    assert fixture._identity_thumbprint(public) == expected
    assert fixture._identity_thumbprint(another) == parse_identity_json(second).thumbprint
    assert fixture._identity_thumbprint(another) != expected
    assert len(expected) == 43 and "private" not in public and "d" not in public

"""Outcome request v1 and v2: each version names its scope list with its own key."""
import pytest

from harness.bulletin_origin import PUBLIC_BULLETIN_ORIGIN
from harness.outcome_bulletin import OutcomeBulletinError, build_preview
from harness.scope import LEGACY_SCOPE_KEY
from tests.test_outcome_bulletin import INDEX_OUTCOME


def _v2_outcome() -> dict:
    outcome = {key: value for key, value in INDEX_OUTCOME.items() if key != LEGACY_SCOPE_KEY}
    outcome["schema"] = "flywheel.outcome-bulletin-request/v2"
    outcome["scope"] = ["Index 2.11.0 release artifacts and targeted router-job tests."]
    return outcome


def test_v2_request_renders_its_scope_list_under_scope():
    body = build_preview(_v2_outcome(), bulletin_base_url=PUBLIC_BULLETIN_ORIGIN)["post"]["body"]
    assert "\n\nScope:\n- Index 2.11.0 release artifacts and targeted router-job tests.\n\n" in body
    assert "Limits:" not in body


@pytest.mark.parametrize("mutate", [
    lambda o: o.update({LEGACY_SCOPE_KEY: ["older key on a v2 request"]}),
    lambda o: o.pop("scope"),
    lambda o: o.update({"schema": "flywheel.outcome-bulletin-request/v1"}),
])
def test_each_request_version_requires_its_own_scope_key(mutate):
    outcome = _v2_outcome()
    mutate(outcome)
    with pytest.raises(OutcomeBulletinError):
        build_preview(outcome, bulletin_base_url=PUBLIC_BULLETIN_ORIGIN)


def test_publication_records_are_v2_with_scope():
    from harness.outcome_bulletin import publish_preview
    preview = build_preview(_v2_outcome(), bulletin_base_url=PUBLIC_BULLETIN_ORIGIN)
    result = publish_preview(preview, grant_ref="gnt_" + "c" * 32)
    assert result["schema"] == "flywheel.outcome-bulletin-publication/v2"
    assert LEGACY_SCOPE_KEY not in result and result["scope"]

"""Zenodo deposit, the fail-closed orchestrator paths: partial and hostile inputs.

Split from test_zenodo_deposit.py to hold the 300-line file gate; the happy-path
and network-leg tests stay there. These cover the deposit() orchestrator's
failure contracts -- a mid-sequence server error carries the created draft's id
and url so the operator can find and discard the orphan, a create-time failure
claims no draft, a mangled or wrong-shape create reply raises DepositError
rather than a raw AttributeError, and a missing publish link refuses before any
publish POST. The transport is injected, so nothing here touches the network.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import zenodo_deposit  # noqa: E402


class FakeTransport:
    """Records every call and returns programmed (status, body) replies in order.

    A reply given as a dict is JSON-encoded; given as bytes it is returned as-is.
    """

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []  # (method, url, headers, body)

    def __call__(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, dict(headers or {}), body))
        status, payload = self._replies.pop(0)
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode()


def _created(dep_id=42, base="https://sandbox.zenodo.org/api"):
    """A create reply shaped like Zenodo's, links included (HATEOAS)."""
    self_url = f"{base}/deposit/depositions/{dep_id}"
    return {
        "id": dep_id,
        "links": {
            "self": self_url,
            "bucket": f"https://sandbox.zenodo.org/api/files/bucket-{dep_id}",
            "publish": f"{self_url}/actions/publish",
        },
    }


TOKEN = "tok_ABC123_never_in_url"


def _md():
    return zenodo_deposit.build_metadata(title="t", description="d",
                                         creators=[{"name": "A, B"}])


def test_a_mid_sequence_failure_carries_the_created_deposition_id_and_url():
    import pytest
    # create() succeeds, so a real draft now exists server-side; then set_metadata
    # fails. The raised error must carry the deposition id and self_url, so the
    # operator can find and discard the orphaned draft instead of re-running blind
    # and creating a second one.
    ft = FakeTransport([
        (201, _created()),               # create -- a draft now exists
        (201, {"key": "anchor.json"}),   # upload
        (500, {"message": "server error"}),  # set metadata blows up
    ])
    with pytest.raises(zenodo_deposit.DepositError) as ei:
        zenodo_deposit.deposit(ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
                               metadata=_md(), sandbox=True, publish=False)
    assert ei.value.deposition_id == 42
    assert str(ei.value.self_url).endswith("/deposit/depositions/42")


def test_a_create_time_failure_claims_no_deposition():
    import pytest
    # If create() itself fails, no deposition exists yet, so the error must not
    # claim a phantom id/url.
    ft = FakeTransport([(500, {"message": "server error"})])
    with pytest.raises(zenodo_deposit.DepositError) as ei:
        zenodo_deposit.deposit(ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
                               metadata=_md(), sandbox=True, publish=False)
    assert ei.value.deposition_id is None
    assert ei.value.self_url is None


def test_a_create_reply_missing_bucket_still_carries_the_created_deposition_id():
    import pytest
    # create() returns 201 with a real id but a reply whose links omit bucket (a
    # HATEOAS violation a mangling proxy could induce). A draft 12345 now exists
    # server-side, so the guard that rejects the partial reply fires *after* create
    # succeeded; the raised error must carry the draft's id and self_url, or the
    # operator cannot find and discard the orphan the reply already named.
    self_url = "https://sandbox.zenodo.org/api/deposit/depositions/12345"
    ft = FakeTransport([
        (201, {"id": 12345, "links": {"self": self_url}}),  # no "bucket"
    ])
    with pytest.raises(zenodo_deposit.DepositError) as ei:
        zenodo_deposit.deposit(ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
                               metadata=_md(), sandbox=True, publish=False)
    assert ei.value.deposition_id == 12345
    assert ei.value.self_url == self_url
    # The guard fires before any upload, so only the create call was made.
    assert len(ft.calls) == 1


def test_a_non_object_json_create_reply_raises_deposit_error_not_attribute_error():
    import pytest
    # A 200 whose body is valid JSON but not an object -- a bare `true`, `null`,
    # number, string, or array -- passes json.loads, so `_parse` returned it
    # unguarded. The next `record.get("links")` in `deposit` then raises
    # AttributeError, which is not the DepositError the module's whole error
    # contract promises. (A non-JSON body already fails closed one branch over;
    # this is the valid-JSON-wrong-shape sibling, and the isinstance guard rejects
    # every non-object scalar and array uniformly.)
    ft = FakeTransport([(200, b"true")])  # create reply: valid JSON, not an object
    with pytest.raises(zenodo_deposit.DepositError):
        zenodo_deposit.deposit(ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
                               metadata=_md(), sandbox=True, publish=False)
    # The guard fires inside create, before any upload, so only create was called.
    assert len(ft.calls) == 1


def test_publish_with_a_create_reply_missing_the_publish_link_refuses_before_posting():
    import pytest
    # publish=True but the create reply omits the publish link (its own distinct
    # guard, separate from the bucket/self one). The deposit runs create, upload,
    # and set_metadata, then refuses rather than POST an unknown publish action;
    # no publish call is made and the draft id is carried for cleanup.
    created = _created()
    created["links"].pop("publish")
    ft = FakeTransport([
        (201, created),                  # create -- bucket + self, no publish link
        (201, {"key": "anchor.json"}),   # upload
        (200, _created()),               # set metadata
    ])
    with pytest.raises(zenodo_deposit.DepositError, match="publish link") as ei:
        zenodo_deposit.deposit(ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
                               metadata=_md(), sandbox=True, publish=True)
    assert ei.value.deposition_id == 42
    assert all("actions/publish" not in u for (_m, u, _h, _b) in ft.calls)

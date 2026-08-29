"""The durability dual anchor: depositing bytes to Zenodo for a citable DOI.

The network is injected, so the whole deposit sequence -- create, upload, set
metadata, and the guarded publish -- is exercised here by a fake transport, never
a live call. The two properties that matter most are checked directly: publish is
never reached unless the caller asks for it (a published DOI cannot be undone), and
the token rides an Authorization header, never a URL.
"""
import hashlib
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


# ---- pure helpers -------------------------------------------------------

def test_api_base_separates_sandbox_from_production():
    assert zenodo_deposit.api_base(sandbox=False) == "https://zenodo.org/api"
    assert zenodo_deposit.api_base(sandbox=True) == "https://sandbox.zenodo.org/api"


def test_build_metadata_wraps_required_fields_under_metadata_key():
    body = zenodo_deposit.build_metadata(
        title="Flywheel confirmatory anchor",
        description="Signed tree head and its anchor record.",
        creators=[{"name": "Harper, Zain Dana"}],
    )
    assert set(body) == {"metadata"}
    md = body["metadata"]
    assert md["title"] == "Flywheel confirmatory anchor"
    assert md["creators"] == [{"name": "Harper, Zain Dana"}]
    assert md["upload_type"] == "dataset"  # default
    assert md["access_right"] == "open" and md["license"]  # open needs a license


def test_build_metadata_rejects_missing_title_and_creators():
    import pytest
    with pytest.raises(zenodo_deposit.DepositError):
        zenodo_deposit.build_metadata(title="", description="x",
                                      creators=[{"name": "A, B"}])
    with pytest.raises(zenodo_deposit.DepositError):
        zenodo_deposit.build_metadata(title="t", description="x", creators=[])


def test_does_not_prove_names_the_durability_limits():
    reasons = zenodo_deposit.does_not_prove()
    assert isinstance(reasons, list) and reasons
    joined = " ".join(reasons)
    assert "NOT_PROVES" in joined


# ---- network legs (injected transport) ----------------------------------

TOKEN = "tok_ABC123_never_in_url"


def test_create_posts_to_depositions_with_bearer_auth_and_no_token_in_url():
    ft = FakeTransport([(201, _created())])
    rec = zenodo_deposit.create(ft, token=TOKEN, sandbox=True)
    assert rec["id"] == 42
    method, url, headers, body = ft.calls[0]
    assert method == "POST"
    assert url == "https://sandbox.zenodo.org/api/deposit/depositions"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in url


def test_upload_file_puts_raw_bytes_to_the_bucket_path():
    ft = FakeTransport([(201, {"key": "head.json"})])
    data = b'{"signed_head": {}}'
    zenodo_deposit.upload_file(
        ft, token=TOKEN,
        bucket_url="https://sandbox.zenodo.org/api/files/bucket-42",
        name="head.json", data=data)
    method, url, headers, body = ft.calls[0]
    assert method == "PUT"
    assert url == "https://sandbox.zenodo.org/api/files/bucket-42/head.json"
    assert body == data
    assert TOKEN not in url


def test_set_metadata_puts_the_metadata_wrapper():
    ft = FakeTransport([(200, _created())])
    md = zenodo_deposit.build_metadata(title="t", description="d",
                                       creators=[{"name": "A, B"}])
    zenodo_deposit.set_metadata(
        ft, token=TOKEN,
        deposition_url="https://sandbox.zenodo.org/api/deposit/depositions/42",
        metadata=md)
    method, url, headers, body = ft.calls[0]
    assert method == "PUT"
    assert json.loads(body) == md


def test_publish_posts_to_the_publish_action():
    ft = FakeTransport([(202, {"doi": "10.5281/zenodo.42"})])
    rec = zenodo_deposit.publish(
        ft, token=TOKEN,
        publish_url="https://sandbox.zenodo.org/api/deposit/depositions/42/actions/publish")
    assert rec["doi"] == "10.5281/zenodo.42"
    method, url, headers, body = ft.calls[0]
    assert method == "POST" and url.endswith("/actions/publish")


def test_a_non_2xx_status_raises_deposit_error():
    import pytest
    ft = FakeTransport([(400, {"message": "bad request"})])
    with pytest.raises(zenodo_deposit.DepositError):
        zenodo_deposit.create(ft, token=TOKEN, sandbox=True)


def test_a_non_json_body_on_a_2xx_status_raises_deposit_error_not_valueerror():
    import pytest
    # An intermediary (proxy, captive portal) can serve a 200 with an HTML body
    # over the real API. The module's whole error contract is DepositError; a raw
    # JSONDecodeError would punch through it unnamed.
    ft = FakeTransport([(200, b"<html>not json</html>")])
    with pytest.raises(zenodo_deposit.DepositError):
        zenodo_deposit.create(ft, token=TOKEN, sandbox=True)


# ---- the orchestrator and its irreversibility guard ---------------------

def _md():
    return zenodo_deposit.build_metadata(title="t", description="d",
                                         creators=[{"name": "A, B"}])


def test_deposit_without_publish_never_calls_the_publish_endpoint():
    ft = FakeTransport([
        (201, _created()),              # create
        (201, {"key": "anchor.json"}),  # upload
        (200, _created()),              # set metadata
    ])
    res = zenodo_deposit.deposit(
        ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
        metadata=_md(), sandbox=True, publish=False)
    assert res["published"] is False and res["doi"] is None
    assert res["deposition_id"] == 42
    assert len(ft.calls) == 3
    assert all("actions/publish" not in u for (_m, u, _h, _b) in ft.calls)


def test_deposit_with_publish_returns_the_doi_and_hits_publish_once():
    ft = FakeTransport([
        (201, _created()),
        (201, {"key": "anchor.json"}),
        (200, _created()),
        (202, {"doi": "10.5281/zenodo.42",
               "links": {"doi": "https://doi.org/10.5281/zenodo.42"}}),
    ])
    res = zenodo_deposit.deposit(
        ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
        metadata=_md(), sandbox=True, publish=True)
    assert res["published"] is True
    assert res["doi"] == "10.5281/zenodo.42"
    publish_calls = [u for (_m, u, _h, _b) in ft.calls if u.endswith("/actions/publish")]
    assert len(publish_calls) == 1


def test_deposit_never_puts_the_token_in_any_url_and_always_bearer_auths():
    ft = FakeTransport([
        (201, _created()),
        (201, {"key": "anchor.json"}),
        (200, _created()),
        (202, {"doi": "10.5281/zenodo.42"}),
    ])
    zenodo_deposit.deposit(
        ft, token=TOKEN, files=[("anchor.json", b'{"a":1}')],
        metadata=_md(), sandbox=True, publish=True)
    for (_m, url, headers, _b) in ft.calls:
        assert TOKEN not in url
        assert headers["Authorization"] == f"Bearer {TOKEN}"


def test_deposit_rejects_an_empty_file_list_before_any_network_call():
    import pytest
    ft = FakeTransport([])
    with pytest.raises(zenodo_deposit.DepositError):
        zenodo_deposit.deposit(ft, token=TOKEN, files=[],
                               metadata=_md(), sandbox=True)
    assert ft.calls == []


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

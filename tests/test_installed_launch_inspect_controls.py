import hashlib
from types import SimpleNamespace

from desktop.tool.installed_launch_inspect import _controls, _controls_ok, _proposal_bound
from harness.inspect_upload_metadata import inspect_data_ref

SHA = "a" * 64


def _proposal(**changes):
    proposal = {
        "schema": "flywheel.gateway-grant-proposal/v1",
        "proposal_ref": "prp_" + "1" * 32,
        "planned_grant_ref": "gnt_" + "1" * 32,
        "action": "import.inspect",
        "destination": {"kind": "import", "ref": f"inspect-json:{SHA[:16]}"},
        "data_refs": [inspect_data_ref(SHA)],
        "operation_sha256": "b" * 64,
        "arguments_sha256": "c" * 64,
    }
    proposal.update(changes)
    return proposal


def test_proposal_bound_rejects_empty_or_malformed_digest_strings():
    ok, observed = _proposal_bound(
        _proposal(operation_sha256="", arguments_sha256="not-a-hash"),
        "gnt_" + "1" * 32,
        SHA,
    )

    assert ok is False
    assert observed["operation_digest_valid"] is False
    assert observed["arguments_digest_valid"] is False
    assert observed["source_bound"] is False


def test_controls_compare_full_paginated_store_eids_not_first_page_count():
    raw = b'{"version":2}'
    sha = hashlib.sha256(raw).hexdigest()
    expected_eid = "eid-main"
    stale_eids = tuple([expected_eid] + [f"eid-stale-{i:02d}" for i in range(49)])
    http = _PagedStoreHttp(raw, sha, stale_eids)
    harness = SimpleNamespace(http=http, c=SimpleNamespace(run_id="run-inspect"))

    controls = _controls(
        harness, 8765, "tok", raw, sha, len(raw), "run.json",
        "jrn_" + "1" * 32, "d" * 64,
        {"X-Flywheel-Grant-Ref": "gnt_" + "0" * 32},
        expected_eid,
    )

    assert controls["changed_source_rejected"] is True
    assert controls["fresh_single_uploaded_row_before_changed_source"] is False
    assert controls["no_new_store_row_after_changed_source"] is False
    assert "eid-hidden-new" in controls["store_eids_after_changed_source"]
    assert _controls_ok(controls) is False


class _PagedStoreHttp:
    def __init__(self, raw, sha, eids):
        self.raw = raw
        self.sha = sha
        self.eids = list(eids)
        self.prepare_count = 0

    def get_json(self, url, token=None, timeout=2.0):
        if token is None:
            return 401, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "AUTH_REQUIRED"}}
        if "/api/import/inspect?" in url:
            from urllib.parse import parse_qs, urlparse
            params = parse_qs(urlparse(url).query)
            limit = int(params.get("limit", ["50"])[0])
            offset = int(params.get("offset", ["0"])[0])
            rows = self.eids[offset:offset + limit]
            return 200, {"schema": "flywheel.inspect-import-list/v1", "items": [{"eid": eid} for eid in rows], "limit": limit, "offset": offset}
        raise AssertionError(url)

    def post_json(self, url, payload, token=None, timeout=2.0):
        if url.endswith("/api/gateway-grants/prepare/import.inspect"):
            self.prepare_count += 1
            suffix = f"{self.prepare_count:032x}"
            source = payload["operation"]["source"]
            return 200, {
                "schema": "flywheel.gateway-grant-proposal/v1",
                "proposal_ref": "prp_" + suffix,
                "planned_grant_ref": "gnt_" + suffix,
                "action": "import.inspect",
                "journey_ref": payload["journey_ref"],
                "expected_event_head": payload["expected_event_head"],
                "client_request_id": payload["client_request_id"],
                "destination": {"kind": "import", "ref": f"inspect-json:{source['sha256'][:16]}"},
                "data_refs": [f"data_inspect.source:{source['sha256'][:32]}"],
                "operation_sha256": "b" * 64,
                "arguments_sha256": "c" * 64,
            }
        if url.endswith("/api/gateway-grants/approve-once"):
            return 200, {"grant_ref": "gnt_" + payload["proposal_ref"][4:]}
        raise AssertionError(url)

    def post_bytes(self, url, raw, headers, token=None, timeout=20.0):
        if headers.get("X-Flywheel-Grant-Ref") == "gnt_" + "f" * 32:
            return 403, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "PERMISSION_REQUIRED"}}
        if raw != self.raw:
            self.eids.append("eid-hidden-new")
            return 409, {"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "SOURCE_DIGEST_MISMATCH"}}
        return 200, {"schema": "unexpected"}

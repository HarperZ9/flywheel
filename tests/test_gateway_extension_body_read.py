import io
import json

import pytest

from harness import gateway
from harness.evidence_extension_contracts import capability_document
from harness.evidence_extension_route import (
    handle_domain_pack_project,
    handle_frontier_axis,
    handle_frontier_project,
    handle_incident_propose,
)


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _ReadLog(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.calls = []

    def read(self, n=-1):
        before = self.tell()
        out = super().read(n)
        self.calls.append((n, before, self.tell(), len(out)))
        return out


def _empty_caps():
    return capability_document(
        journey={"schema": "flywheel.evidence-journey-projection/v2",
                 "event_head_sha256": "0" * 64},
        incident_contract=None, frontier_contract=None, pack_contracts=[],
        containment={"process": False})


CASES = [
    ("/api/journeys/extensions/incident-propose", handle_incident_propose,
     {"capability_sha256": "a" * 64, "case": {"id": "case"}, "projection": {}}),
    ("/api/journeys/extensions/frontier-project", handle_frontier_project,
     {"capability_sha256": "a" * 64, "claim": {"id": "claim"},
      "journey_ref": "jrn_" + "a" * 32, "event_head_sha256": "b" * 64}),
    ("/api/journeys/extensions/frontier-axis", handle_frontier_axis,
     {"capability_sha256": "a" * 64, "journey_ref": "jrn_" + "a" * 32,
      "expected_event_head": "b" * 64, "client_request_id": "req-1",
      "grant_ref": "gnt_" + "a" * 32, "claim_id": "claim",
      "axis": "evidence", "patch": {"value": 1}}),
    ("/api/journeys/extensions/domain-pack-project", handle_domain_pack_project,
     {"capability_sha256": "a" * 64, "manifest": {"pack_id": "pack"}}),
]


@pytest.mark.parametrize(("path", "direct", "body"), CASES)
def test_gateway_extension_routes_parse_already_read_body_once(path, direct, body, tmp_path):
    caps = _empty_caps()
    expected = direct(body, caps, gateway._Handler.clock) if direct is handle_frontier_axis else direct(body, caps)
    assert expected[1] == 403

    raw = json.dumps(body).encode()
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = path
    handler.headers = _Headers({"Content-Length": str(len(raw))})
    handler.rfile = _ReadLog(raw)
    handler.root = tmp_path
    handler.run_root = str(tmp_path / "runs")
    handler.flywheel_home = tmp_path / "home"
    handler.owner_ref = "owner_" + "a" * 32
    captured = {}
    handler._json = lambda obj, code=200: captured.update(body=obj, code=code)

    handler._post()

    assert captured["code"] == expected[1]
    assert captured["body"]["error"]["code"] == expected[0]["error"]["code"]
    assert handler.rfile.calls == [(len(raw), 0, len(raw), len(raw))]

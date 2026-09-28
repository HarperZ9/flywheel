import json
import re
from pathlib import Path

from harness.evidence_json import canonical_bytes
from harness.inspect_evidence import import_inspect_log
from harness.inspect_upload_metadata import INSPECT_MEDIA_TYPES
from harness.inspect_unit_contract_route import (
    REQUEST_SCHEMA as UNIT_CONTRACT_REQUEST_SCHEMA,
    UNIT_CONTRACT_UPLOAD_MEDIA_TYPE,
)


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_FIXTURE = ROOT / "desktop" / "test" / "fixtures" / "native_inspect_real_report.json"
DESKTOP_CLIENT = ROOT / "desktop" / "lib" / "client" / "gateway_inspect.dart"
HTTP_SUPPORT = ROOT / "tests" / "inspect_http_support.py"
PINNED_FIXTURE = ROOT / "tests" / "fixtures" / "inspect" / "v1" / "epochs-invalidated.fixture.json"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _single(pattern: str, text: str, *, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    assert match is not None
    return match.group(1)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_desktop_fixture_matches_python_importer_for_pinned_epochs_invalidated():
    expected = _json(DESKTOP_FIXTURE)
    pinned = _json(PINNED_FIXTURE)

    actual = import_inspect_log(canonical_bytes(pinned["inspect_log"]))

    assert actual == expected


def test_desktop_upload_contract_matches_python_routes():
    desktop = DESKTOP_CLIENT.read_text(encoding="utf-8")
    helper_media = _single(
        r'INSPECT_UPLOAD_CONTENT_TYPE\s*=\s*"([^"]+)"',
        HTTP_SUPPORT.read_text(encoding="utf-8"),
    )
    raw_branch = _compact(_single(
        r"if\s*\(unit\s*==\s*null\)\s*\{(.*?)\n\s*return;",
        desktop,
        flags=re.DOTALL,
    ))
    sidecar_media = _single(
        r"const\s+_inspectUnitContractUploadContentType\s*=\s*'([^']+)';",
        desktop,
    )
    sidecar_branch = _compact(desktop[desktop.index("final body = utf8.encode"):])

    assert helper_media == "application/json"
    assert helper_media in INSPECT_MEDIA_TYPES
    assert f"request.headers['Content-Type']='{helper_media}';" in raw_branch
    assert "request.headers['Content-Length']='${upload.byteLength}';" in raw_branch
    assert "request.headers['X-Flywheel-Inspect-Sha256']=upload.sha256;" in raw_branch
    assert (
        "request.headers['X-Flywheel-Inspect-Byte-Length']='${upload.byteLength}';"
        in raw_branch
    )
    assert "request.bodyBytes=upload.bytes;" in raw_branch

    assert sidecar_media == UNIT_CONTRACT_UPLOAD_MEDIA_TYPE
    assert sidecar_media not in INSPECT_MEDIA_TYPES
    assert f"'schema':'{UNIT_CONTRACT_REQUEST_SCHEMA}'" in sidecar_branch
    assert "'inspect_sha256':upload.sha256" in sidecar_branch
    assert "'inspect_byte_length':upload.byteLength" in sidecar_branch
    assert "'inspect_json_base64':base64Encode(upload.bytes)" in sidecar_branch
    assert "'unit_contract_json_base64':base64Encode(unit.bytes)" in sidecar_branch
    assert (
        "request.headers['Content-Type']=_inspectUnitContractUploadContentType;"
        in sidecar_branch
    )
    assert "request.headers['Content-Length']='${body.length}';" in sidecar_branch
    assert "request.bodyBytes=body;" in sidecar_branch

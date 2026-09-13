import json
import re
from pathlib import Path

from harness.evidence_json import canonical_bytes
from harness.inspect_evidence import import_inspect_log


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_FIXTURE = ROOT / "desktop" / "test" / "fixtures" / "native_inspect_real_report.json"
DESKTOP_CLIENT = ROOT / "desktop" / "lib" / "client" / "gateway_inspect.dart"
HTTP_SUPPORT = ROOT / "tests" / "inspect_http_support.py"
PINNED_FIXTURE = ROOT / "tests" / "fixtures" / "inspect" / "v1" / "epochs-invalidated.fixture.json"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _single(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    assert match is not None
    return match.group(1)


def test_desktop_fixture_matches_python_importer_for_pinned_epochs_invalidated():
    expected = _json(DESKTOP_FIXTURE)
    pinned = _json(PINNED_FIXTURE)

    actual = import_inspect_log(canonical_bytes(pinned["inspect_log"]))

    assert actual == expected


def test_desktop_upload_media_type_matches_python_http_helper():
    helper_media = _single(
        r'INSPECT_UPLOAD_CONTENT_TYPE\s*=\s*"([^"]+)"',
        HTTP_SUPPORT.read_text(encoding="utf-8"),
    )
    desktop_media = _single(
        r"\.\.headers\['Content-Type'\]\s*=\s*'([^']+)'",
        DESKTOP_CLIENT.read_text(encoding="utf-8"),
    )

    assert helper_media == "application/json"
    assert desktop_media == helper_media

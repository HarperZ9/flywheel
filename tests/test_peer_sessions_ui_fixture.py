"""The gate between the engine's field names and the Dart surface that reads them.

The route gate counts paths, so it stays green when a field is renamed inside a
response a view already reaches. Three checks close that gap: the committed Dart
fixture still has the shape a fresh build produces, every field the view
subscripts is a field that shape carries, and nothing about the generating
machine survives into the committed file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.peer_session_fixtures import ACCOUNT_CANARY, CANARY
from tests.peer_sessions_ui_fixture import PATHS, ROOT_TOKEN, build_bodies, canonical, skeleton

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "desktop" / "test" / "peer_sessions_fixture.dart"
VIEW = REPO / "desktop" / "lib" / "views" / "peer_sessions_view.dart"
BODY_RE = re.compile(r"^  '([^']+)': r'''\n(.*?)''',$", re.M | re.S)
SUBSCRIPT_RE = re.compile(r"\['([a-z][a-z0-9_]*)'\]")
REBUILD = "rebuild it with tests/peer_sessions_ui_fixture.build_bodies"


@pytest.fixture(scope="module")
def committed() -> dict:
    """The three bodies as the Dart test will decode them."""
    text = FIXTURE.read_text(encoding="utf-8")
    found = {path: json.loads(raw) for path, raw in BODY_RE.findall(text)}
    assert list(found) == list(PATHS), "the fixture lists different paths than the route serves"
    return found


def test_the_committed_fixture_still_has_the_shape_the_route_produces(committed, tmp_path):
    """A field renamed, added or dropped in the engine changes this shape. The Dart
    test would keep passing against the old fixture, so the comparison lives here."""
    fresh = build_bodies(tmp_path)
    for path in PATHS:
        assert canonical(skeleton(committed[path])) == canonical(skeleton(fresh[path])), (
            f"{path} no longer matches the committed fixture; {REBUILD}")


def test_every_field_the_view_reads_is_a_field_the_engine_emits(committed):
    """The view reads its data by string subscript, which no Dart type checks. A
    subscript naming a key nothing emits renders as null and reads as honest."""
    keys = set()
    for body in committed.values():
        _collect_keys(body, keys)
    read = set(SUBSCRIPT_RE.findall(VIEW.read_text(encoding="utf-8")))
    assert read, "no field reads were found in the view, so this gate proves nothing"
    unknown = sorted(read - keys)
    assert unknown == [], f"the view reads fields the engine does not emit: {unknown}"


def test_the_view_reads_something_from_each_response_it_requests(committed):
    """Requesting a route and rendering nothing from it would pass the gate above
    while leaving the route unsurfaced in every way that matters."""
    view = VIEW.read_text(encoding="utf-8")
    read = set(SUBSCRIPT_RE.findall(view))
    for path in PATHS:
        assert f"'{path}'" in view, f"{path} is not requested by the view"
        top = set(committed[path]) & read
        assert top, f"the view requests {path} and reads no field of it"


def test_the_committed_fixture_names_no_machine_and_carries_no_transcript_text(committed):
    """It is a file in the repository. A temporary path or a line of transcript in
    it would be published by the next clone, not by a deliberate decision."""
    text = FIXTURE.read_text(encoding="utf-8")
    for secret in (CANARY, ACCOUNT_CANARY, "example.invalid", "AppData", "Users", "Temp"):
        assert secret not in text, f"{secret} reached the committed fixture"
    paths = [s["source"]["path"] for s in committed[PATHS[0]]["sessions"]]
    assert paths and all(p.startswith(ROOT_TOKEN) for p in paths), paths


def test_the_shape_comparison_notices_a_renamed_field(committed):
    """Without this the test above would still pass if skeleton() returned a
    constant, which is the way a shape gate usually stops working."""
    altered = json.loads(json.dumps(committed[PATHS[0]]))
    altered["discovered_by_harness"] = altered.pop("discovered_by_harness")
    assert canonical(skeleton(altered)) == canonical(skeleton(committed[PATHS[0]]))
    altered["sessions_found"] = altered.pop("discovered")
    assert canonical(skeleton(altered)) != canonical(skeleton(committed[PATHS[0]]))
    widened = json.loads(json.dumps(committed[PATHS[0]]))
    widened["discovered"] = str(widened["discovered"])
    assert canonical(skeleton(widened)) != canonical(skeleton(committed[PATHS[0]]))


def _collect_keys(value, out: set) -> None:
    if isinstance(value, dict):
        out.update(value)
        for item in value.values():
            _collect_keys(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_keys(item, out)

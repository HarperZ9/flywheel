"""No personal voice ships. The built wheel and the plugin bundle carry no voice
profile, no identity file, no export and no store folder.

The house voice ships as its specs (house_voice_v1.json and house_voice_v2.json),
which are written from
design principles and names no person's writing as its source."""
import json
import zipfile

import pytest

from claude_plugin_helpers import ROOT, load

PROFILE_SCHEMAS = ("articulate/voice-profile/v1", "articulate/voice-export/v1")
STORE_NAMES = ("identity.json", "/voice/")


def _offending(name, data):
    text = data.decode("utf-8", "replace")
    problems = [s for s in PROFILE_SCHEMAS if f'"schema": "{s}"' in text or f'"schema":"{s}"' in text]
    if any(n in "/" + name.replace("\\", "/") for n in STORE_NAMES):
        problems.append("store path")
    if name.endswith(".json"):
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if isinstance(value, dict) and ("per_sample" in value or "attestation" in value
                                        or "owner_id" in value):
            problems.append("profile-shaped json")
    return problems


def test_the_scan_catches_a_planted_profile():
    planted = json.dumps({"schema": "articulate/voice-profile/v1"}).encode()
    assert _offending("x/mine.json", planted)
    assert _offending("articulate/voice/identity.json", b"{}")
    assert _offending("x/identity-copy.json", b'{"owner_id": "abc"}')
    assert not _offending("articulate/data/house_voice_v1.json", b'{"schema": "articulate/house-voice/v1"}')
    assert not _offending(".claude-plugin/marketplace.json", b'{"owner": {"name": "x"}}')


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    builders = pytest.importorskip("hatchling.builders.wheel")
    out = tmp_path_factory.mktemp("wheel")
    path = next(iter(builders.WheelBuilder(str(ROOT)).build(directory=str(out), versions=["standard"])))
    return path


def test_the_wheel_carries_no_profile(wheel):
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        for spec in ("house_voice_v1.json", "house_voice_v2.json"):
            assert any(n.endswith("articulate/data/" + spec) for n in names), spec
        bad = {n: _offending(n, zf.read(n)) for n in names}
    assert not {n: p for n, p in bad.items() if p}


def test_the_plugin_bundle_carries_no_profile(tmp_path):
    build = load("build_claude_plugin")
    out = tmp_path / "bundle"
    written = build.build(out, repo=ROOT)
    assert "src/articulate/data/house_voice_v1.json" in written
    assert "src/articulate/data/house_voice_v2.json" in written
    assert "server/house_hook.py" in written
    bad = {}
    for rel in written:
        problems = _offending(rel, (out / rel).read_bytes())
        if problems:
            bad[rel] = problems
    assert not bad


@pytest.mark.parametrize("name", ["house_voice_v1.json", "house_voice_v2.json"])
def test_the_house_spec_says_no_person_was_modelled(name):
    spec = json.loads((ROOT / "src" / "articulate" / "data" / name).read_text(encoding="utf-8"))
    assert spec["provenance"]["person_writing_used"] is False
    assert not {"owner", "owner_id", "attestation", "per_sample"} & set(spec)

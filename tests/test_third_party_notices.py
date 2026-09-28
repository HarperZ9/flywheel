"""The installer's third-party notice names what the engine actually ships.

The notice is copied into the installer (desktop/scripts/build_installer.ps1),
so a pin that moves without it leaves the installer naming the wrong version
or license. Each check below reads the pin from its manifest, never from a
constant here, so a pin bump fails this file until the notice follows.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NOTICE = REPO / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt"


def _text() -> str:
    return NOTICE.read_text(encoding="utf-8")


def _lane_rows() -> list[dict]:
    path = REPO / "packaging" / "python-lane-payloads.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _license_id(row: dict) -> str:
    value = row["owner_project"]["license"]
    return value["text"] if isinstance(value, dict) else value


def test_every_frozen_lane_is_named_with_its_pin_and_license():
    text = _text()
    for row in _lane_rows():
        project = row["owner_project"]
        line = next((item for item in text.splitlines()
                     if item.startswith(f"{project['name']} {project['version']} ")), None)
        assert line is not None, f"notice lacks {project['name']} {project['version']}"
        assert row["owner_tag"] in line and row["owner_commit"][:12] in line, line
        assert _license_id(row) in line and f"(lane {row['lane']})" in line, line
    assert "licenses/python-lanes/<lane>/" in text


def test_the_bundled_node_runtime_and_learn_match_their_pins():
    manifest = json.loads((REPO / "packaging" / "node-lane-payloads.json")
                          .read_text(encoding="utf-8"))
    text = _text()
    node = manifest["node_runtime"]
    assert f"Node.js {node['version']} (win-x64, LTS)" in text
    assert node["sha256"] in text and node["members"]["LICENSE"] in text
    for lane in manifest["lanes"]:
        if lane.get("hold"):
            assert f"{lane['package']} {lane['version']}) is not in this build" in text
        else:
            assert f"{lane['package']} {lane['version']}" in text


def test_the_python_runtime_and_openssl_are_named_with_their_shipped_texts():
    text = _text()
    for token in ("Python Software Foundation License Version 2",
                  "licenses/python/LICENSE.txt",
                  "licenses/python/incorporated/",
                  "OpenSSL 3.0", "Apache License 2.0",
                  "libcrypto-3.dll", "libssl-3.dll",
                  "cryptography", ".dist-info/licenses/",
                  "Microsoft Distributable Code"):
        assert token in text, token


def test_every_studio_runtime_component_is_named_with_its_source_pin():
    sources = json.loads((REPO / "packaging" / "studio-runtime-sources.json")
                         .read_text(encoding="utf-8"))
    text = _text()
    for name, pin in sources["components"].items():
        repo_name = pin["repo"].rsplit("/", 1)[-1].removesuffix(".git")
        line = next((item for item in text.splitlines() if item.startswith(repo_name + " ")),
                    None)
        assert line is not None, f"notice lacks {repo_name}"
        assert pin["ref"][:12] in line, line


def test_the_notice_stays_plain_and_short():
    text = _text()
    assert "—" not in text
    assert len(text.splitlines()) <= 300

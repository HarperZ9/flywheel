"""Bounded MCP skill resources: public skills are packaged, named, and closed."""

import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from harness.local_mcp import handle
from harness.skill_resources import list_resources, read_resource


def _req(method, rid=1, params=None):
    request = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        request["id"] = rid
    if params is not None:
        request["params"] = params
    return request


def test_flywheel_evidence_skill_resources_advertise_versions_and_hashes():
    """Removing the manifest/hash metadata makes clients import anonymous bytes."""
    doc = list_resources()
    rows = {row["uri"]: row for row in doc["resources"]}

    skill = rows["flywheel://skills/flywheel-evidence-task/SKILL.md"]
    constraints = rows[
        "flywheel://skills/flywheel-evidence-task/references/constraints.md"
    ]

    assert doc["schema"] == "flywheel.skill-resources/v1"
    assert skill["name"] == "flywheel-evidence-task/SKILL.md"
    assert skill["version"] == "0.1.0"
    assert len(skill["sha256"]) == 64
    assert skill["mimeType"] == "text/markdown"
    assert constraints["name"] == "flywheel-evidence-task/references/constraints.md"
    assert len(constraints["sha256"]) == 64


def test_read_resource_returns_the_packaged_public_skill_text():
    """Returning filesystem text instead of package data breaks installed wheels."""
    uri = "flywheel://skills/flywheel-evidence-task/SKILL.md"

    doc = read_resource(uri)
    content = doc["contents"][0]

    assert content["uri"] == uri
    assert content["mimeType"] == "text/markdown"
    assert "# Flywheel Evidence Task" in content["text"]
    assert "Read [references/constraints.md]" in content["text"]


def test_unknown_and_traversal_uris_are_rejected_without_filesystem_reads():
    """Normalizing arbitrary paths would turn a skill import into a file reader."""
    for uri in [
        "flywheel://skills/flywheel-evidence-task/../SKILL.md",
        "file:///private/denied-key",
        "flywheel://skills/flywheel-evidence-task/references/missing.md",
    ]:
        with pytest.raises(KeyError, match="unknown skill resource"):
            read_resource(uri)


def test_local_mcp_advertises_and_reads_skill_resources():
    """Forgetting MCP resource methods leaves packaged skills unreachable to clients."""
    listed = handle(_req("resources/list"))["result"]
    uris = {row["uri"] for row in listed["resources"]}
    uri = "flywheel://skills/flywheel-evidence-task/references/constraints.md"

    read = handle(_req("resources/read", params={"uri": uri}))["result"]

    assert uri in uris
    assert read["contents"][0]["uri"] == uri
    assert "Liveness is not readiness" in read["contents"][0]["text"]


@pytest.mark.parametrize("params", [None, [], "unexpected", 3, {"uri": []}])
def test_bad_resource_params_are_protocol_errors_not_server_crashes(params):
    response = handle(_req("resources/read", params=params))
    assert response["error"]["code"] == -32602


def test_mcp_resources_match_downloadable_skill_and_manifest():
    """A stale packaged copy must not silently differ from the human download."""
    plugin = Path(__file__).resolve().parents[1] / "plugins" / "flywheel-evidence-task"
    version = json.loads((plugin / ".codex-plugin/plugin.json").read_text("utf-8"))["version"]
    for row in list_resources()["resources"]:
        text = read_resource(row["uri"])["contents"][0]["text"]
        assert text == (plugin / "skills" / row["name"]).read_text("utf-8")
        assert row["version"] == version
        assert row["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert row["bytes"] == len(text.encode("utf-8"))


def test_installed_wheel_contains_public_skill_resources(tmp_path):
    """Omitting package-data passes from source but ships a wheel with no skill."""
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(dist)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wheel = next(dist.glob("flywheel_verify-*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert "harness/skill_resources/flywheel-evidence-task/SKILL.md" in names
    assert (
        "harness/skill_resources/flywheel-evidence-task/references/constraints.md"
        in names
    )

    code = (
        "from harness.skill_resources import read_resource;"
        "doc=read_resource('flywheel://skills/flywheel-evidence-task/references/constraints.md');"
        "assert 'For video or forum feedback' in doc['contents'][0]['text'];"
        "assert 'Liveness is not readiness' in doc['contents'][0]['text']"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(wheel)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

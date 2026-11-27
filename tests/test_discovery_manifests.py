"""Validation tests for Wave 32A discovery manifests (CITATION, codemeta, llms, MCP registry)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP_SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
EXPECTED_SERVERS = ("articulate", "canon", "flywheel", "gather", "index")


def test_citation_codemeta_and_llms_stay_aligned_and_hygienic() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ver_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert ver_match is not None
    version = ver_match.group(1)

    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert "\u2014" not in cff
    assert f'version: "{version}"' in cff
    assert "orcid: \"https://orcid.org/0009-0001-7175-5393\"" in cff

    meta_raw = (ROOT / "codemeta.json").read_text(encoding="utf-8")
    assert "\u2014" not in meta_raw
    meta = json.loads(meta_raw)
    assert meta["@context"] == "https://doi.org/10.5063/schema/codemeta-2.0"
    assert meta["@type"] == "SoftwareSourceCode"
    assert meta["name"] == "Flywheel"
    assert meta["version"] == version
    assert meta["codeRepository"] == "https://github.com/HarperZ9/flywheel"

    llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert "\u2014" not in llms
    for needle in ("CITATION.cff", "codemeta.json", "docs/mcp-registry/flywheel.server.json", "flywheel gate"):
        assert needle in llms


def test_official_mcp_registry_manifests_match_2025_12_11_schema() -> None:
    reg_dir = ROOT / "docs" / "mcp-registry"
    found = sorted(p.name.removesuffix(".server.json") for p in reg_dir.glob("*.server.json"))
    assert found == list(EXPECTED_SERVERS)

    for slug in EXPECTED_SERVERS:
        raw = (reg_dir / f"{slug}.server.json").read_text(encoding="utf-8")
        assert "\u2014" not in raw
        data = json.loads(raw)
        assert data["$schema"] == MCP_SCHEMA
        assert data["name"] == f"io.github.harperz9/{slug}"
        assert isinstance(data["title"], str) and data["title"].strip()
        assert isinstance(data["description"], str) and len(data["description"]) <= 120
        assert isinstance(data["version"], str) and data["version"].strip()
        assert data["repository"]["source"] == "github"
        assert isinstance(data["packages"], list) and len(data["packages"]) >= 1
        pkg = data["packages"][0]
        assert pkg["registryType"] == "pypi"
        assert pkg["transport"]["type"] == "stdio"

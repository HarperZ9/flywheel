"""The Flywheel Verify Claude plugin folder, held to the directory's file rules.

Each check here is a rule the directory's pre-submission checklist blocks or
holds on, or a promise the README makes. Passing them does not predict the
portal's result, which runs more checks than this file can see.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import pytest

from harness import check_mcp
from scripts import check_claim_language as claims
from scripts import check_public_instructions as hygiene

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "flywheel-verify"
MANIFEST_KEYS = {"$schema", "name", "displayName", "version", "description", "author",
                 "homepage", "repository", "license", "keywords", "metadata",
                 "defaultEnabled", "dependencies", "settings", "userConfig", "channels",
                 "skills", "commands", "agents", "hooks", "mcpServers", "lspServers",
                 "outputStyles", "workflows", "experimental"}
DEVICE_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _json(rel: str) -> dict:
    return json.loads((PLUGIN / rel).read_text(encoding="utf-8"))


def _version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["version"]


def _files() -> list[Path]:
    return sorted(p for p in PLUGIN.rglob("*") if p.is_file())


def _prose(text: str) -> str:
    return re.sub(r"```.*?```", " ", text, flags=re.S)


def test_the_manifest_has_the_fields_every_surface_reads():
    manifest = _json(".claude-plugin/plugin.json")
    assert set(manifest) <= MANIFEST_KEYS
    assert re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", manifest["name"])
    assert manifest["name"] == "flywheel-verify"
    assert manifest["version"] == _version()
    assert manifest["license"] == "FSL-1.1-MIT" and (PLUGIN / "LICENSE").is_file()
    assert manifest["author"]["name"] and manifest["description"]
    assert manifest["displayName"].isascii() and manifest["author"]["name"].isascii()
    for key in ("homepage", "repository"):
        assert urlparse(manifest[key]).scheme == "https"
    policy = manifest["metadata"]["privacy_policies"]
    assert policy and all(u.startswith("https://") and u.endswith("#privacy-policy")
                          for u in policy)


def test_the_server_starts_from_the_pinned_published_package():
    config = _json(".mcp.json")
    assert config == {"mcpServers": {"check": {
        "command": "uvx",
        "args": ["--from", f"flywheel-verify=={_version()}", "flywheel-check-mcp"]}}}
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["scripts"]
    assert scripts["flywheel-check-mcp"] == "harness.check_mcp:main"


def test_no_package_manager_config_redirects_the_launcher():
    # A registry or index setting in a plugin that uses uvx is blocked.
    names = {"uv.toml", "pyproject.toml", "pip.conf", "pip.ini", ".npmrc", ".pypirc"}
    assert not [p for p in _files() if p.name in names]


def test_every_callable_tool_name_fits_in_64_characters():
    prefix = "mcp__plugin_flywheel-verify_check__"
    names = [t["name"] for t in check_mcp.TOOLS]
    assert names and all(len(prefix + n) <= 64 for n in names)


def test_the_layout_follows_the_directory_file_rules():
    files = _files()
    assert (PLUGIN / "README.md").is_file()
    assert not (PLUGIN / "bin").exists() and not (PLUGIN / "CLAUDE.md").exists()
    assert sorted(p.name for p in (PLUGIN / ".claude-plugin").iterdir()) == ["plugin.json"]
    assert len(files) <= 512
    lowered: dict[str, Path] = {}
    for path in files:
        rel = path.relative_to(PLUGIN)
        assert not path.is_symlink(), rel
        assert path.name not in {".DS_Store", "Thumbs.db", "desktop.ini"}, rel
        for part in rel.parts:
            assert ":" not in part and not part.endswith((".", " ")), rel
            assert part.split(".")[0].lower() not in DEVICE_NAMES, rel
        key = rel.as_posix().lower()
        assert key not in lowered, (rel, lowered.get(key))
        lowered[key] = rel
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            assert path.stat().st_size < 256 * 1024, rel
            path.read_text(encoding="utf-8")    # text only: no binary payloads


def test_gitattributes_only_turns_conversion_off():
    for path in PLUGIN.rglob(".gitattributes"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pattern, *attrs = line.split()
            assert attrs == ["-text"], line
            assert not re.search(r"filter|eol|export-", line), line


def test_the_readme_has_the_listing_material():
    text = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert len(_prose(text).split()) >= 40
    section = text.split("## Privacy Policy", 1)[1].split("\n## ", 1)[0].lower()
    for topic in ("data collected", "use and storage", "third-party sharing",
                  "retention", "contact"):
        assert f"**{topic}" in section, topic
    assert "pypi.org" in section and "no tool arguments or results" in section
    prompts = text.split("## Try it", 1)[1].split("\n## ", 1)[0]
    assert len(re.findall(r"^\d\. \"", prompts, re.M)) >= 3
    assert "medical, legal, or financial advice" in text
    assert "does not show that the source is right" in text


def test_the_skill_front_matter_parses_and_names_its_folder():
    path = PLUGIN / "skills" / "check-before-answering" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    head = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert head, "front matter missing"
    fields = dict(line.split(": ", 1) for line in head.group(1).splitlines())
    assert fields["name"] == path.parent.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert 0 < len(fields["description"]) <= 1024 and ": " not in fields["description"]
    assert len(text.splitlines()) < 500
    for tool in ("check_answer", "domain_packs", "verify_bundle"):
        assert tool in text


def test_the_sample_answers_do_what_the_readme_says():
    contract = _json("examples/check-answer/contract.json")
    sources = {"rates.json": _json("examples/check-answer/rates.json")}
    results = {}
    for name in ("answer.json", "answer-wrong.json"):
        reply = check_mcp.call_tool({"name": "check_answer", "arguments": {
            "contract": contract, "answer": _json(f"examples/check-answer/{name}"),
            "sources": sources}})["structuredContent"]
        results[name] = (reply["verdict"], reply["release"])
    assert results == {"answer.json": ("PASS", "RELEASE"),
                       "answer-wrong.json": ("FAIL", "HOLD")}


@pytest.mark.parametrize("path", sorted(p for p in PLUGIN.rglob("*.md")),
                         ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_public_text_is_clean(path):
    text = path.read_text(encoding="utf-8")
    assert "\u2014" not in text, "em dash"
    assert hygiene.scan(path, ROOT) == []
    assert claims.scan(path) == []
    assert not re.search(r"\b(?:operator|lanes?|gates?)\b", text, re.I)


def test_the_marketplace_lists_the_plugin_and_describes_itself():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(
        encoding="utf-8"))
    assert market["description"]
    entry = next(p for p in market["plugins"] if p["name"] == "flywheel-verify")
    assert entry["source"] == "./plugins/flywheel-verify"

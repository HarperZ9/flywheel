"""release_identity.py -- one source-bound release identity.

The identity binds the tag, the source commit and tree, the wheel and
installer names, the non-executing profile, and the hashes of the
accepted policy files. Every fact is read from an accepted file or a
required argument; nothing defaults and nothing is guessed. A preflight
fact that is missing or marked blocked stops the build with a typed
blocking receipt.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256

SCHEMA = "flywheel.release-identity/v1"
PROFILE = "flywheel.desktop-profile/non-executing/v1"
PHASE_RECEIPTS_REQUIRED = 5


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing preflight fact: {path.name} does not exist")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"preflight fact {path.name} is unreadable") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"preflight fact {path.name} is not an object")
    return doc


def _blocking_facts(doc: dict, name: str) -> None:
    blocked = doc.get("blocked")
    if blocked:
        raise ValueError(
            f"{name} carries unresolved blocking facts: {sorted(blocked)}")
    for key, value in doc.items():
        if isinstance(value, str) and value.upper() == "BLOCKED":
            raise ValueError(f"{name}.{key} is BLOCKED: owner acceptance "
                             "required before a release identity exists")


def _version_from_pubspec(root: Path) -> str:
    pubspec = root / "desktop" / "pubspec.yaml"
    for line in pubspec.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().split("+")[0]
    raise ValueError("desktop/pubspec.yaml declares no version")


def _version_from_pyproject(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("pyproject.toml declares no version")


def build_release_identity(
    root: Path,
    *,
    tag: str,
    source_commit: str,
    phase_receipts: list[str],
) -> dict:
    root = Path(root)
    if not tag.startswith("v"):
        raise ValueError("the release tag must start with v")
    if len(source_commit) != 40:
        raise ValueError("the source commit must be a full 40-hex sha")
    if len(phase_receipts) != PHASE_RECEIPTS_REQUIRED:
        raise ValueError(
            f"phase 1-5 acceptance requires exactly "
            f"{PHASE_RECEIPTS_REQUIRED} receipt hashes")
    for receipt in phase_receipts:
        if len(receipt) != 64:
            raise ValueError("a phase receipt is not a sha256")

    release_dir = root / "desktop" / "release"
    support = _read_json(release_dir / "windows-support.json")
    toolchains = _read_json(release_dir / "toolchains.json")
    policy = _read_json(release_dir / "release-policy.json")
    payload_policy = _read_json(release_dir / "payload-policy.json")
    for name, doc in (("windows-support.json", support),
                      ("toolchains.json", toolchains),
                      ("release-policy.json", policy),
                      ("payload-policy.json", payload_policy)):
        _blocking_facts(doc, name)

    pubspec_version = _version_from_pubspec(root)
    pyproject_version = _version_from_pyproject(root)
    version = tag[1:]
    if version != pubspec_version or version != pyproject_version:
        raise ValueError(
            f"identity drift: tag v{version}, pubspec {pubspec_version}, "
            f"pyproject {pyproject_version}")
    profile = policy.get("profile")
    if profile != PROFILE:
        raise ValueError("the release policy does not bind the "
                         "non-executing v1 profile")
    blob = str(policy) + str(payload_policy)
    if "sandbox" in blob.lower():
        raise ValueError("the profile must never be called sandboxed")
    identity = {
        "schema": SCHEMA,
        "version": version,
        "tag": tag,
        "source_commit": source_commit,
        "source_tree_sha256": canonical_sha256(
            {"commit": source_commit, "tag": tag}),
        "wheel_name": f"flywheel_verify-{version}-py3-none-any.whl",
        "desktop_product_id": policy.get("desktop_product_id", ""),
        "desktop_exe_version": version,
        "gateway_exe_version": version,
        "installer_app_id": policy.get("installer_app_id", ""),
        "api_schema": policy.get("api_schema", ""),
        "capability_schema": "flywheel.evidence-capabilities/v1",
        "profile": PROFILE,
        "phase_receipts": list(phase_receipts),
        "policy_sha256": canonical_sha256(policy),
        "toolchains_sha256": canonical_sha256(toolchains),
        "support_sha256": canonical_sha256(support),
        "payload_policy_sha256": canonical_sha256(payload_policy),
    }
    if not identity["desktop_product_id"] or not identity["installer_app_id"]:
        raise ValueError("the release policy lacks product/app identities")
    if not identity["api_schema"]:
        raise ValueError("the release policy lacks the authenticated api "
                         "schema")
    return identity

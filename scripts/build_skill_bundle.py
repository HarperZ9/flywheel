"""Build reproducible, allowlisted plugin and standalone skill downloads."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent
NAME = "flywheel-evidence-task"
PLUGIN = ROOT / "plugins" / NAME
SKILL_FILES = (
    "SKILL.md", "agents/openai.yaml", "references/constraints.md",
    "examples/public-lane-count.md", "examples/bulletin-feedback.md",
    "examples/negative-readiness-shortcut.md",
)
PLUGIN_FILES = (
    ".codex-plugin/plugin.json", ".claude-plugin/plugin.json",
    "README.md", "PRIVACY.md", "LICENSE", "LICENSE-ATTRIBUTION.md", "CHANGELOG.md",
)
# Directory listing icon. Binary, so it is copied byte for byte.
PLUGIN_BINARY_FILES = (".claude-plugin/icon.png",)
PORTABLE_KEYS = ("name", "version", "description", "author", "homepage",
                 "repository", "license", "keywords")


def public_text(path: Path) -> bytes:
    """UTF-8 text with canonical newlines, independent of Git checkout settings."""
    return path.read_text(encoding="utf-8").encode("utf-8")


def bundle(out: Path) -> dict:
    """No network, execution, private inventory, or recursive source scan."""
    manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text("utf-8"))
    version = manifest["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("invalid package version")
    claude = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text("utf-8"))
    if (manifest.get("name") != NAME or claude.get("name") != NAME
            or claude.get("version") != version):
        raise ValueError("manifest identity or version mismatch")
    portable = {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                **{key: manifest[key] for key in PORTABLE_KEYS if key in manifest},
                "extensions": {"com.openai": {"interface": manifest["interface"]}}}
    skill = PLUGIN / "skills" / NAME
    files = {name: public_text(PLUGIN / name) for name in PLUGIN_FILES}
    files.update({name: (PLUGIN / name).read_bytes() for name in PLUGIN_BINARY_FILES})
    files["plugin.json"] = (json.dumps(portable, indent=2) + "\n").encode("utf-8")
    files.update({f"skills/{NAME}/{name}": public_text(skill / name)
                  for name in SKILL_FILES})
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for kind, entries in (
        ("plugin", files),
        ("skill", {**{name: public_text(skill / name) for name in SKILL_FILES},
                   "LICENSE": files["LICENSE"]}),
    ):
        destination = out / f"{NAME}-{version}-{kind}.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(f"{NAME}/{name}", (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        results.append({"file": destination.name, "bytes": destination.stat().st_size,
                        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                        "files": len(entries)})
    receipt = {"schema": "flywheel.skill-bundle/v1", "name": NAME,
               "version": version, "artifacts": results,
               "does_not_prove": "Host installation, semantic truth, or marketplace approval."}
    (out / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n", "utf-8")
    (out / "SHA256SUMS").write_text(
        "".join(f"{row['sha256']}  {row['file']}\n" for row in results), "utf-8")
    return receipt


def verify_release(checksums: Path, accepted_sha256: str) -> int:
    """Verify exactly the two archive bytes named by an accepted receipt."""
    data = checksums.read_bytes()
    if hashlib.sha256(data).hexdigest() != accepted_sha256:
        raise ValueError("checksum receipt does not match accepted SHA-256")
    rows = []
    for line in data.decode("utf-8").splitlines():
        match = re.fullmatch(
            rf"([0-9a-f]{{64}})  ({NAME}-(\d+\.\d+\.\d+)-(plugin|skill)\.zip)", line)
        if not match:
            raise ValueError("invalid archive checksum receipt")
        rows.append(match.groups())
    if (len(rows) != 2 or {row[3] for row in rows} != {"plugin", "skill"}
            or len({row[2] for row in rows}) != 1):
        raise ValueError("incomplete or inconsistent archive checksum receipt")
    expected = {row[1] for row in rows}
    if {path.name for path in checksums.parent.glob("*.zip")} != expected:
        raise ValueError("archive set differs from checksum receipt")
    for digest, name, _, _ in rows:
        archive = checksums.parent / name
        if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError(f"archive hash mismatch: {name}")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--verify", type=Path, help="accepted checksum receipt path")
    parser.add_argument("--accepted-sha256")
    args = parser.parse_args()
    if args.verify:
        if not args.accepted_sha256:
            parser.error("--verify requires --accepted-sha256")
        print(json.dumps({"verified_archives": verify_release(args.verify, args.accepted_sha256)}))
    else:
        print(json.dumps(bundle(args.out), indent=2))

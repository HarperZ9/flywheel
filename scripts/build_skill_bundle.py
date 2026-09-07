"""Build reproducible, allowlisted plugin and standalone skill downloads."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
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
    "README.md", "LICENSE", "LICENSE-ATTRIBUTION.md", "CHANGELOG.md",
)


def public_text(path: Path) -> bytes:
    """UTF-8 text with canonical newlines, independent of Git checkout settings."""
    return path.read_text(encoding="utf-8").encode("utf-8")


def bundle(out: Path) -> dict:
    """No network, execution, private inventory, or recursive source scan."""
    manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text("utf-8"))
    version = manifest["version"]
    if not isinstance(version, str) or not all(c in "0123456789." for c in version):
        raise ValueError("invalid package version")
    skill = PLUGIN / "skills" / NAME
    files = {name: public_text(PLUGIN / name) for name in PLUGIN_FILES}
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(bundle(parser.parse_args().out), indent=2))

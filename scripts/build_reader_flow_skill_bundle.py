"""Build the reproducible Reader Flow Review standalone skill download."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent
NAME = "reader-flow-review"
VERSION = "0.1.0"
TAG_PLAN = f"skill-{NAME}-v{VERSION}"
SKILL = ROOT / "skills" / NAME
SKILL_FILES = (
    "SKILL.md",
    "README.md",
    "SOURCE-ATTRIBUTION.md",
    "EVALUATION.md",
)
ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)
SCHEMA = "flywheel.skill-bundle/v1"

_PRIVATE_PATTERNS = (
    (re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)"), "local drive path"),
    (re.compile(r"\.scratch", re.IGNORECASE), "scratch path marker"),
    (re.compile(r"\bUsers[\\/]", re.IGNORECASE), "user home path"),
    (re.compile(r"\b(run_dir|output_file|prompt_file|event_log)\b",
                re.IGNORECASE), "raw run metadata field"),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public_text(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    for rx, reason in _PRIVATE_PATTERNS:
        if rx.search(text):
            raise ValueError(f"{path.relative_to(ROOT)} contains {reason}")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _archive_entries() -> dict[str, bytes]:
    entries = {name: _public_text(SKILL / name) for name in SKILL_FILES}
    entries["LICENSE"] = _public_text(ROOT / "LICENSE")
    return entries


def _write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(f"{NAME}/{name}", ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def bundle(out: Path) -> dict:
    """Build a standalone skill archive from allowlisted source files."""
    entries = _archive_entries()
    out.mkdir(parents=True, exist_ok=True)
    destination = out / f"{NAME}-{VERSION}-skill.zip"
    _write_zip(destination, entries)
    artifact = {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination.read_bytes()),
        "files": len(entries),
    }
    receipt = {
        "schema": SCHEMA,
        "name": NAME,
        "version": VERSION,
        "tag_plan": TAG_PLAN,
        "artifacts": [artifact],
        "does_not_prove": (
            "Host installation, live automatic invocation, writing quality, "
            "semantic correctness, held-out generalization, marketplace "
            "approval, or Flywheel platform release."
        ),
    }
    (out / "manifest.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                       encoding="utf-8")
    (out / "SHA256SUMS").write_text(
        f"{artifact['sha256']}  {artifact['file']}\n", encoding="utf-8"
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(bundle(parser.parse_args().out), indent=2))

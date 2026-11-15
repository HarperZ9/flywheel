"""Best-effort demo - not runtime-verified by author.

End-to-end demo of the public-surface-sweeper Python API.

It builds two throwaway repositories in a temp directory:
  1. a clean repo with all required files, public/developer README delivery,
     and a substantive visual asset, and
  2. a "dirty" repo missing files and containing an em dash plus a
     GitHub-token-shaped value,
then runs scan / summarize / format / proof-packet on each.

Run from the repo root:

    PYTHONPATH=src python examples/demo.py

(or `python examples/demo.py` once the package is installed).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from public_surface_sweeper.sweeper import (
    format_summary,
    format_text,
    proof_surface_packet,
    scan,
    summarize_findings,
)

EM_DASH = chr(0x2014)
# Token-shaped string assembled at runtime so this file itself stays clean.
FAKE_GITHUB_TOKEN = "ghp_" + "ABCdef1234567890ABCdef1234567890zz"


def build_clean_repo(root: Path) -> None:
    brand_dir = root / "docs" / "brand"
    brand_dir.mkdir(parents=True)
    (brand_dir / "demo-hero.png").write_bytes(b"fake image")
    (root / "README.md").write_text(
        "# Demo\n\n"
        "![Demo hero](docs/brand/demo-hero.png)\n\n"
        "> A clear public description for a useful tool.\n\n"
        "## Why it matters\n\n"
        "This explains the public value.\n\n"
        "## Try it\n\n"
        "```bash\npython -m demo\n```\n\n"
        "## For developers\n\n"
        "```bash\npython -m pytest\n```\n",
        encoding="utf-8",
    )
    for name in ("LICENSE", "AUTHORS.md", "CONTRIBUTING.md"):
        (root / name).write_text("ok\n", encoding="utf-8")


def build_dirty_repo(root: Path) -> None:
    # Missing AUTHORS.md and CONTRIBUTING.md on purpose.
    (root / "README.md").write_text(
        f"title\nbad {EM_DASH} dash\n{FAKE_GITHUB_TOKEN}\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")


def report(label: str, root: Path) -> None:
    findings = scan(root)
    summary = summarize_findings(findings)

    print(f"\n=== {label} ===")
    print("-- text --")
    print(format_text(findings))
    print("-- summary --")
    print(format_summary(summary))
    print("-- proof packet --")
    print(json.dumps(proof_surface_packet(root, findings), indent=2))


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        clean = base / "clean-repo"
        clean.mkdir()
        build_clean_repo(clean)
        report("clean repo", clean)

        dirty = base / "dirty-repo"
        dirty.mkdir()
        build_dirty_repo(dirty)
        report("dirty repo", dirty)


if __name__ == "__main__":
    main()

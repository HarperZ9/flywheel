"""reproduce.py -- check this bundle without trusting whoever sent it.

Run: python reproduce.py

Needs a bare Python interpreter. No pip install, no network, no GPU. If this
prints MATCH, every file matches the manifest hash it shipped with and every
receipt digest was recomputed from its own body.

Read the does_not_prove section of manifest.json before treating MATCH as more
than it is.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    bad = []
    for f in manifest["files"]:
        rel = f["path"]
        if rel.startswith("/") or ".." in rel.split("/"):
            bad.append(f"unsafe path {rel}")
            continue
        p = HERE / rel
        if not p.is_file():
            bad.append(f"missing {rel}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            bad.append(f"hash mismatch {rel}")
    print("\n".join(bad) if bad
          else f"MATCH: {len(manifest['files'])} file(s) verified")
    print()
    print("what this does not prove:")
    for s in manifest.get("does_not_prove", []):
        print("  - " + s)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

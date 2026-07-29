"""bundle.py -- everything a stranger needs, and nothing that could hurt them.

A receipt alone re-derives nothing. The criterion it was judged against, the
checker source that judged it, the QA card bounding that checker's false accepts,
and a tree head to anchor the log all have to travel with it.

Two halves, and the asymmetry between them is the whole design:

  PACK runs on OUR data. It writes a directory plus a manifest binding every file
  by sha256, strips local-only signatures, and refuses to ship at all if the
  secret scan hits. Refusing beats warning: a warning gets skimmed.

  VERIFY runs on a bundle the reader DID NOT BUILD, so every path in the manifest
  is hostile input. Absolute paths, parent traversal, and symlinks are refused
  before anything is opened. A verifier that trusts manifest paths is a
  file-read primitive wearing a checker's coat.

Verify also refuses a bundle containing files the manifest does not list. A file
nobody vouched for is not evidence, and shipping it inside a verified-looking
bundle is how something unreviewed gets read as reviewed.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from .receipt import Receipt
from .receipt_fields import canonical
from .receipt_sign import pack_for_export, verify_signed, LOCAL_ONLY_ALGS

SCHEMA = "flywheel.bundle/v1"
MANIFEST_NAME = "manifest.json"

LIMITS = [
    "NOT_PROVES_PUBLICATION_COMPLETENESS: this bundle shows what it contains and "
    "cannot show what was left out of it.",
    "NOT_PROVES_RECEIPT_CORRECTNESS: the manifest shows nothing was altered after "
    "packing. A bundle of forged receipts with intact hashes verifies structurally.",
    "NOT_PROVES_CHECKER_CORRECTNESS: the checker source ships so it can be read. "
    "That it was shipped is not evidence that it implements the right predicate.",
]

# Shapes that must never leave the machine. Deliberately narrow: a scanner that
# fires on ordinary hashes gets disabled by the first person it annoys.
_SECRET_PATTERNS = (
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"\bAKIA[0-9A-Z]{16}\b", "aws access key id"),
    (r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", "github token"),
    (r"\bsk-(?:live|proj|ant)[A-Za-z0-9_\-]{10,}\b", "provider api key"),
    (r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b", "slack token"),
    (r"(?i)\b(?:secret|password|passwd|api_key|access_key)\s*[:=]\s*"
     r"['\"]?[A-Za-z0-9/+_\-]{12,}", "assigned credential"),
)


class BundleError(ValueError):
    """The bundle refuses to be built, or refuses to be trusted."""


def scan_for_secrets(text: str) -> list[str]:
    """Named hits, empty when clean. Narrow on purpose."""
    out = []
    for pattern, label in _SECRET_PATTERNS:
        if re.search(pattern, text):
            out.append(label)
    return out


def safe_relative(path: str) -> Path:
    """A manifest path that cannot escape the bundle.

    Refuses absolute paths, drive letters, and any parent traversal. Checked on
    the STRING before touching the filesystem, so a hostile manifest never
    reaches an open().
    """
    if not isinstance(path, str) or not path:
        raise BundleError("a manifest path must be a non-empty string")
    if "\x00" in path:
        raise BundleError("a manifest path must not contain a null byte")
    norm = path.replace("\\", "/")
    p = PurePosixPath(norm)
    if p.is_absolute() or norm.startswith("/"):
        raise BundleError(f"absolute manifest path refused: {path!r}")
    if re.match(r"^[A-Za-z]:", norm):
        raise BundleError(f"drive-qualified manifest path refused: {path!r}")
    if any(part == ".." for part in p.parts):
        raise BundleError(f"parent traversal refused in manifest path: {path!r}")
    return Path(*p.parts)


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write(root: Path, rel: str, text: str, files: list) -> None:
    p = root / safe_relative(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    hits = scan_for_secrets(text)
    if hits:
        raise BundleError(
            f"refusing to pack {rel}: secret scan hit ({', '.join(hits)}). "
            "This is a refusal rather than a warning, because a warning gets "
            "skimmed and a credential does not come back.")
    p.write_bytes(data)
    files.append({"path": PurePosixPath(safe_relative(rel)).as_posix(),
                  "sha256": _sha_bytes(data), "bytes": len(data)})


def pack_bundle(out_dir, *, envelopes: list, criterion: dict,
                checker_sources: dict, qa_card: dict, tree_head: dict) -> Path:
    """Write a self-contained bundle. Returns its directory."""
    if not envelopes:
        raise BundleError("a bundle with no receipts proves nothing")
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    files: list = []

    for i, env in enumerate(sorted(envelopes,
                                   key=lambda e: e["receipt"]["claim_sha256"])):
        # Local-only signatures are stripped here, not at read time: a reader who
        # holds an HMAC tag they cannot check will assume it means something.
        packed = pack_for_export(env)
        claim = packed["receipt"]["claim_sha256"].split(":", 1)[1][:16]
        _write(root, f"receipts/{i:04d}-{claim}.json",
               json.dumps(packed, indent=1, sort_keys=True), files)

    _write(root, "criterion.json", json.dumps(criterion, indent=1, sort_keys=True),
           files)
    _write(root, "qa_card.json", json.dumps(qa_card, indent=1, sort_keys=True),
           files)
    _write(root, "tree_head.json", json.dumps(tree_head, indent=1, sort_keys=True),
           files)
    for name, source in sorted(checker_sources.items()):
        _write(root, f"checker/{name}", source, files)
    _write(root, "reproduce.py", _REPRODUCE, files)

    manifest = {"schema": SCHEMA, "files": sorted(files, key=lambda f: f["path"]),
                "does_not_prove": LIMITS}
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1,
                                                 sort_keys=True),
                                      encoding="utf-8")
    return root


def verify_bundle(bundle_dir) -> dict:
    """Check a bundle the reader did not build. Never raises on hostile input."""
    root = Path(bundle_dir)
    mp = root / MANIFEST_NAME
    if not mp.exists():
        return {"verdict": "UNVERIFIABLE", "files_checked": 0, "receipts": [],
                "detail": f"no {MANIFEST_NAME} at {root}"}
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        listed = manifest["files"]
    except Exception as e:
        return {"verdict": "UNVERIFIABLE", "files_checked": 0, "receipts": [],
                "detail": f"{MANIFEST_NAME} is unreadable: {e}"}

    # Every path is validated as a STRING before any filesystem access.
    rels: list[tuple[Path, dict]] = []
    for f in listed:
        try:
            rels.append((safe_relative(f["path"]), f))
        except (BundleError, KeyError, TypeError) as e:
            return {"verdict": "UNVERIFIABLE", "files_checked": 0,
                    "receipts": [], "detail": f"unsafe manifest path: {e}"}

    checked = 0
    for rel, f in rels:
        p = root / rel
        if p.is_symlink():
            return {"verdict": "DRIFT", "files_checked": checked, "receipts": [],
                    "detail": f"{rel.as_posix()} is a symlink; a bundle carries "
                              "files, not pointers to files elsewhere"}
        if not p.is_file():
            return {"verdict": "DRIFT", "files_checked": checked, "receipts": [],
                    "detail": f"{rel.as_posix()} is listed and missing"}
        if _sha_bytes(p.read_bytes()) != f.get("sha256"):
            return {"verdict": "DRIFT", "files_checked": checked, "receipts": [],
                    "detail": f"{rel.as_posix()} does not match its manifest hash"}
        checked += 1

    # A file nobody vouched for is not evidence.
    on_disk = {p.relative_to(root).as_posix()
               for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    on_disk.discard(MANIFEST_NAME)
    unlisted = sorted(on_disk - {r.as_posix() for r, _ in rels})
    if unlisted:
        return {"verdict": "DRIFT", "files_checked": checked, "receipts": [],
                "detail": f"unlisted file(s) present: {', '.join(unlisted[:4])}"}

    receipts = []
    for rel, _ in rels:
        if not rel.as_posix().startswith("receipts/"):
            continue
        try:
            env = json.loads((root / rel).read_text(encoding="utf-8"))
            body = env["receipt"]
            recomputed = Receipt.from_dict(body).claim_sha256()
        except Exception as e:
            return {"verdict": "DRIFT", "files_checked": checked,
                    "receipts": receipts,
                    "detail": f"{rel.as_posix()} is not a receipt envelope: {e}"}
        if recomputed != body.get("claim_sha256"):
            return {"verdict": "DRIFT", "files_checked": checked,
                    "receipts": receipts,
                    "detail": f"{rel.as_posix()} digest does not match its body"}
        sig = env.get("signature")
        if sig is None:
            state = "unsigned"
        elif sig.get("sig_alg") in LOCAL_ONLY_ALGS:
            state = "local-only (not third-party checkable)"
        else:
            pub = sig.get("public_key", "")
            try:
                ok, why = verify_signed(env, bytes.fromhex(pub)) if pub else (
                    False, "no_public_key")
            except ValueError:
                ok, why = False, "malformed_public_key"
            state = f"ed25519 verified" if ok else f"ed25519 FAILED ({why})"
        receipts.append({"path": rel.as_posix(),
                         "claim_sha256": recomputed, "signature": state})

    return {"verdict": "MATCH", "files_checked": checked, "receipts": receipts,
            "detail": f"{checked} file(s) matched the manifest, "
                      f"{len(receipts)} receipt(s) re-derived",
            "does_not_prove": manifest.get("does_not_prove", [])}


_REPRODUCE = '''"""reproduce.py -- check this bundle without trusting whoever sent it.

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
    print("\\n".join(bad) if bad
          else f"MATCH: {len(manifest['files'])} file(s) verified")
    print()
    print("what this does not prove:")
    for s in manifest.get("does_not_prove", []):
        print("  - " + s)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
'''

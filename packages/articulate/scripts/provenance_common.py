"""Shared helpers for the known-provenance corpus.

The manifest at corpus/provenance/manifest.json lists every document with its
SHA-256, its class (human, ai or mixed), its genre and how it came to exist.
Documents marked "repo" live under corpus/provenance/. Documents marked
"local" come from corpora whose licence forbids redistribution; they live
under a local root given with --local-root, and only their hashes are
committed.
"""
import hashlib
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROV = ROOT / "corpus" / "provenance"
MANIFEST = PROV / "manifest.json"
DEFAULT_LOCAL = pathlib.Path(os.environ.get("ARTICULATE_PROVENANCE_LOCAL", "provenance-local"))
SCHEMA = "articulate/provenance-manifest/v1"


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest():
    if not MANIFEST.is_file():
        return {"schema": SCHEMA, "documents": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(man):
    man["documents"].sort(key=lambda d: d["id"])
    MANIFEST.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")


def upsert(man, doc):
    """Add a document; an id already present must carry the same hash."""
    for old in man["documents"]:
        if old["id"] == doc["id"]:
            if old["sha256"] != doc["sha256"]:
                raise ValueError(f"{doc['id']}: hash differs from the manifest; refusing to overwrite")
            return False
    man["documents"].append(doc)
    return True


def doc_path(doc, local_root=DEFAULT_LOCAL):
    base = PROV if doc["location"] == "repo" else pathlib.Path(local_root)
    return base / doc["path"]


def write_text(doc, text, local_root=DEFAULT_LOCAL):
    path = doc_path(doc, local_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def read_checked(doc, local_root=DEFAULT_LOCAL):
    """The document text, or None when it is missing or its hash differs."""
    path = doc_path(doc, local_root)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return text if sha256_text(text) == doc["sha256"] else None


def words(text):
    return len(text.split())

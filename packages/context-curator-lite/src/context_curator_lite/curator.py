"""Curate sanitized planning context from local assistant sessions.

This tool does not copy raw transcripts. It extracts short planning-like
fragments, redacts secret-shaped values, and scrubs direct identifiers
(emails, IPs, URLs, hashes) before writing local artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .telos_envelope import build_context_envelope


KEYWORDS = re.compile(
    r"\b("
    r"todo|next|plan|roadmap|blocker|blocked|handoff|resume|continue|"
    r"migrat|integrat|curat|commit|push|branch|repo|worktree|dirty|"
    r"architecture|design|invariant|whitepaper|research|idea|context|"
    r"session|scope|manifest|ledger"
    r")\b",
    re.IGNORECASE,
)

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(bearer|token|api[_-]?key|password|secret)\s*[:=]\s*\S+"),
]

IDENTIFIER_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"https?://(?!github\.com/)[^\s)>\"]+"), "<url>"),
    (re.compile(r"\b[A-Fa-f0-9]{40,64}\b"), "<hash>"),
]

EXTENSIONS = {".jsonl", ".json", ".md", ".txt", ".log"}
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FRAGMENT = 420


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def source_ref(path: Path, roots: list[Path]) -> str:
    try:
        resolved_path = path.resolve()
    except OSError:
        resolved_path = path
    for root in roots:
        try:
            resolved_root = root.resolve()
            rel = resolved_path.relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        rel_text = rel.as_posix()
        return path.name if rel_text in ("", ".") else rel_text
    return path.name


def iter_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def scrub(text: str) -> str:
    text = text.replace("\x00", " ")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted-secret>", text)
    for pattern, replacement in IDENTIFIER_PATTERNS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_FRAGMENT:
        text = text[: MAX_FRAGMENT - 3].rstrip() + "..."
    return text


def classify(text: str) -> str:
    low = text.lower()
    if any(word in low for word in ("blocker", "blocked", "error", "failed")):
        return "blocker"
    if any(word in low for word in ("todo", "next", "resume", "continue", "handoff")):
        return "next-action"
    if any(word in low for word in ("architecture", "design", "invariant", "whitepaper", "research", "idea")):
        return "idea"
    if any(word in low for word in ("repo", "worktree", "branch", "commit", "push", "dirty", "migrat")):
        return "repo-context"
    return "context"


def fragments_from_file(path: Path) -> Iterable[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return
    except OSError:
        return

    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        if KEYWORDS.search(line):
                            yield line
                        continue
                    for text in iter_strings(item):
                        if KEYWORDS.search(text):
                            yield text
        elif suffix == ".json":
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                try:
                    item = json.load(handle)
                except json.JSONDecodeError:
                    handle.seek(0)
                    for line in handle:
                        if KEYWORDS.search(line):
                            yield line
                else:
                    for text in iter_strings(item):
                        if KEYWORDS.search(text):
                            yield text
        else:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if KEYWORDS.search(line):
                        yield line
    except OSError:
        return


def source_files(roots: list[Path]) -> Iterable[Path]:
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in EXTENSIONS:
            paths.append(root)
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                paths.append(path)
    yield from sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)


def main(
    roots: list[str] | None = None,
    out_dir: str | Path | None = None,
    limit: int = 2500,
    per_file_limit: int = 12,
    telos_envelope: bool = False,
) -> int:
    if roots is None or out_dir is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--root", action="append", required=True)
        parser.add_argument("--out-dir", required=True)
        parser.add_argument("--limit", type=int, default=2500)
        parser.add_argument("--per-file-limit", type=int, default=12)
        parser.add_argument("--telos-envelope", action="store_true")
        args = parser.parse_args()
        roots = args.root
        out_dir = args.out_dir
        limit = args.limit
        per_file_limit = args.per_file_limit
        telos_envelope = args.telos_envelope

    roots = [Path(item) for item in roots]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    records: list[dict[str, str]] = []
    scanned = 0
    matched = 0

    for path in source_files(roots):
        scanned += 1
        file_records = 0
        for raw in fragments_from_file(path):
            matched += 1
            text = scrub(raw)
            if not text or len(text) < 20:
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            if digest in seen:
                continue
            seen.add(digest)
            source = source_ref(path, roots)
            records.append(
                {
                    "kind": classify(text),
                    "source": source,
                    "source_sha256_prefix": stable_id(source),
                    "text": text,
                }
            )
            file_records += 1
            if file_records >= per_file_limit:
                break
            if len(records) >= limit:
                break
        if len(records) >= limit:
            break

    now = datetime.now()
    timestamp = now.isoformat(timespec="seconds")
    date_stamp = now.date().isoformat()
    jsonl_path = out_dir / f"curated-session-context-{date_stamp}.jsonl"
    md_path = out_dir / f"CURATED-SESSION-CONTEXT-{date_stamp}.md"
    manifest_path = out_dir / "curated-session-context-manifest.json"
    envelope_path = out_dir / "project-telos-context-envelope.json"

    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    counts = Counter(record["kind"] for record in records)
    with md_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Curated Session Context\n\n")
        handle.write("Local-only sanitized extraction. Raw transcripts were not copied.\n\n")
        handle.write("## Counts\n\n")
        handle.write(f"- Generated: {timestamp}\n")
        handle.write(f"- Source files scanned: {scanned}\n")
        handle.write(f"- Raw keyword matches before sanitization: {matched}\n")
        handle.write(f"- Curated records: {len(records)}\n")
        for kind, count in sorted(counts.items()):
            handle.write(f"- {kind}: {count}\n")
        handle.write("\n## Curated Items\n\n")
        for index, record in enumerate(records, 1):
            handle.write(f"### {index}. {record['kind']}\n\n")
            handle.write(f"- Source hash: `{record['source_sha256_prefix']}`\n")
            handle.write(f"- Text: {record['text']}\n\n")

    outputs = [md_path.name, jsonl_path.name, manifest_path.name]
    if telos_envelope:
        outputs.append(envelope_path.name)

    manifest = {
        "generated": timestamp,
        "root_count": len(roots),
        "root_sha256_prefixes": [stable_id(str(root.resolve())) for root in roots],
        "outputs": outputs,
        "absolute_paths_included": False,
        "raw_transcripts_copied": False,
        "source_files_scanned": scanned,
        "raw_keyword_matches": matched,
        "curated_records": len(records),
        "counts": dict(counts),
    }
    if telos_envelope:
        envelope = build_context_envelope(records, roots, manifest)
        envelope_path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

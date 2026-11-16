"""Stage 6, diffuse: an export that a stranger can re-derive, and a blocklist for what cannot be shared.

This writes files locally. Publishing is a later step for the author. A source enters the export only when
the access record passes on evidence and says redistribution yes. Everything else goes on the blocklist with
its reason, and its values, including derived values, stay out.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from .access import SourceRecord, sha256_file
from .filecheck import check_licence
from .schema import validate


def decide(rec: SourceRecord, root, today="2026-10-31") -> tuple:
    bad = check_licence(rec, root, today)
    if rec.redistribution != "yes":
        bad.append(f"redistribution is {rec.redistribution}")
    return (not bad), bad


def export(sources: dict, records_by_source: dict, out, code_hash: str, checks_run: list, today="2026-10-31") -> dict:
    """sources maps source_id to (SourceRecord, folder). records_by_source maps source_id to a JSONL path."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    included, blocked = [], []
    for sid, (rec, root) in sorted(sources.items()):
        ok, why = decide(rec, root, today)
        path = records_by_source.get(sid)
        if not ok:
            blocked.append(dict(source_id=sid, title=rec.title, licence=rec.licence, basis=rec.basis, reasons=why))
            continue
        if not path:
            continue
        name = f"{sid}.jsonl"
        n, bad = 0, 0
        with open(path, encoding="utf8") as f, open(out / name, "w", encoding="utf8", newline="\n") as g:
            for line in f:
                r = json.loads(line)
                bad += bool(validate(r))
                if r.get("source_id") != sid or r.get("licence") != rec.licence:
                    raise ValueError(f"{sid}: record {r.get('id')} carries another source or licence")
                g.write(line)
                n += 1
        included.append(dict(source_id=sid, file=name, records=n, invalid=bad, sha256=sha256_file(out / name), licence=rec.licence, licence_quote=rec.licence_quote,
                             terms_url=rec.terms_url, terms_sha256=rec.terms_sha256, terms_read_at=rec.terms_read_at, attribution=rec.title, url=rec.url,
                             input_files=[dict(name=x["name"], sha256=x["sha256"], url=x["url"]) for x in rec.files]))
    manifest = dict(schema="datapipe.export/1", built=today, code_sha256=code_hash, included=included, verified=checks_run)
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf8")
    (out / "BLOCKLIST.json").write_text(json.dumps(blocked, indent=1, ensure_ascii=False), encoding="utf8")
    return dict(manifest=manifest, blocked=blocked)


def verify_export(out) -> list:
    """Re-derive what can be re-derived offline: file hashes and record validity. A stranger also reruns structure from the raw input."""
    out, problems = Path(out), []
    m = json.loads((out / "MANIFEST.json").read_text(encoding="utf8"))
    blocked = {b["source_id"] for b in json.loads((out / "BLOCKLIST.json").read_text(encoding="utf8"))}
    for e in m["included"]:
        if e["source_id"] in blocked:
            problems.append(f"{e['source_id']} is both exported and blocked")
        if sha256_file(out / e["file"]) != e["sha256"]:
            problems.append(f"{e['file']} hash differs")
    return problems

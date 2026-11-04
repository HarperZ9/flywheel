"""Index reference and inspiration notes (Markdown or text) by paragraph.

Each paragraph becomes a 'reference' unit with a pointer to its byte offset
and the nearest heading, so design and research work can find a concept and
go back to its source. Reference units carry use=internal in their meta:
they are for transformation into our own ideas, never for copying into
public work.
"""

import hashlib
import os

from harness.recall_index import store
from harness.recall_index.ingest import emit

MAX_PARA = 6000


def _paragraphs(f):
    """Yield (offset, heading, text) per blank-line separated paragraph."""
    offset, start, buf, heading = 0, 0, [], ""
    for raw in f:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("#"):
            heading = line.lstrip("#").strip()[:160]
        if line.strip():
            if not buf:
                start = offset
            buf.append(line)
        elif buf:
            yield start, heading, "\n".join(buf)[:MAX_PARA]
            buf = []
        offset += len(raw)
    if buf:
        yield start, heading, "\n".join(buf)[:MAX_PARA]


def ingest_reference(con, path: str, label: str = "") -> dict:
    path = os.path.abspath(path)
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()  # reference notes are small
    state = store.source_state(con, path)
    size = os.path.getsize(path)
    if state and state[0] == sha and state[1] == size:
        return {"source": path, "read": 0, "units": 0, "skipped": 0}
    if state:
        store.drop_source(con, path)
    session = label or os.path.basename(os.path.dirname(path)) + "/" + os.path.basename(path)
    ctx = {"source": path, "scope": "reference", "session": session, "units": 0,
           "skipped": 0}
    with open(path, "rb") as f:
        for seq, (off, heading, text) in enumerate(_paragraphs(f)):
            unit = {"kind": "reference", "text": text,
                    "meta": {"heading": heading, "use": "internal"}}
            ctx["units"] += emit(con, ctx, off, "", unit, seq)
    store.save_source(con, path, "reference", session, sha, size, size, ctx["units"],
                      ctx["skipped"])
    con.commit()
    return {"source": path, "read": size, "units": ctx["units"], "skipped": ctx["skipped"]}

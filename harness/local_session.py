"""local_session.py — a witnessed, resumable session ledger for the local agent.

The differentiator over aider / gptme / open-interpreter: the agent's whole
trajectory (user turns, assistant turns, tool calls, tool results) is a
hash-chained ledger. Each entry binds to its predecessor, so a saved session is
tamper-evident and re-verifiable — you can prove the recorded run is the run that
happened. Saves to / resumes from JSONL with zero dependencies.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "0" * 64


def _h(*parts: str) -> str:
    m = hashlib.sha256()
    for p in parts:
        m.update(b"\x1f")
        m.update(p.encode("utf-8"))
    return m.hexdigest()


@dataclass
class Entry:
    seq: int
    kind: str            # user | assistant | tool_call | tool_result
    content: str
    meta: dict
    prev_hash: str
    entry_hash: str

    @staticmethod
    def compute_hash(seq: int, kind: str, content: str, meta: dict, prev_hash: str) -> str:
        return _h(str(seq), kind, content,
                  json.dumps(meta, sort_keys=True, ensure_ascii=False), prev_hash)


@dataclass
class SessionLedger:
    entries: list[Entry] = field(default_factory=list)

    def append(self, kind: str, content: str, meta: "dict | None" = None) -> Entry:
        meta = meta or {}
        seq = len(self.entries)
        prev = self.entries[-1].entry_hash if self.entries else GENESIS
        eh = Entry.compute_hash(seq, kind, content, meta, prev)
        e = Entry(seq, kind, content, meta, prev, eh)
        self.entries.append(e)
        return e

    def verify(self) -> bool:
        """Re-derive the chain: every entry's hash and prev-link must hold."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.seq != i or e.prev_hash != prev:
                return False
            if Entry.compute_hash(e.seq, e.kind, e.content, e.meta, e.prev_hash) != e.entry_hash:
                return False
            prev = e.entry_hash
        return True

    def checkpoint(self) -> str:
        """A single root over the chain (the head hash), for a compact receipt."""
        return self.entries[-1].entry_hash if self.entries else GENESIS

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(e), ensure_ascii=False) for e in self.entries)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_jsonl())

    @classmethod
    def load(cls, path: str) -> "SessionLedger":
        led = cls()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    led.entries.append(Entry(**json.loads(line)))
        return led

    def transcript(self) -> list[dict]:
        """The user/assistant turns (drop tool bookkeeping) for prompting a resume."""
        return [{"role": e.kind, "content": e.content}
                for e in self.entries if e.kind in ("user", "assistant")]

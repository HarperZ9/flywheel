"""action_witness.py -- bind a Flywheel action to the exact bytes it moved.

byte_witness seals bytes. This names the action that moved them and keeps one
chain per run, so a run's actions are ordered and tamper-evident together
rather than one record at a time.

An action leaves two records: the bytes that went in, and the bytes that came
back. Both land in the same chain, so the order the actions ran in is part of
what a stranger rechecks, and an action inserted after the fact has to forge
every link that follows it.

The records travel and the bytes do not. A run's log can go where the arguments
and the output never could, and anyone holding the content can still check it.

Writing a record can fail, and a failed write is not hidden. The chain in memory
advances anyway, so the next record points back at a link the log does not
contain, and the log reads as broken rather than as intact. A silent hole would
be the one failure this layer cannot afford.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .byte_witness import (GENESIS, Span, Witness, WitnessError, append,
                           does_not_prove as byte_does_not_prove, records)
from .byte_witness_verify import verify_chain
from .evidence_json import canonical_bytes

ACTION_SCHEMA = "flywheel.action-witness/v1"
LOG_NAME = "action-witness.jsonl"

INPUT = "input"
OUTPUT = "output"

CANONICAL_JSON = "canonical-json"
UTF8 = "utf-8"


def _text(value: object) -> object:
    """A context value the record can carry. Anything exotic becomes its text.

    A caller's odd value must not be what stops an action from being witnessed,
    so this normalizes rather than refuses. Numbers, text, and booleans keep
    their type, because those are what a reader filters and sorts on.
    """
    if isinstance(value, (bool, str, int)):
        return value
    return str(value)


def _context(run_id: str, action: str, kind: str, seq: int, encoding: str,
             extra: dict | None) -> dict:
    held = {"schema": ACTION_SCHEMA, "run_id": str(run_id), "action": str(action),
            "kind": str(kind), "seq": seq if isinstance(seq, int) and not isinstance(seq, bool) else 0,
            "encoding": str(encoding)}
    for key, value in (extra or {}).items():
        name = str(key)
        if name not in held:  # the action facts are not overwritable by a caller
            held[name] = _text(value)
    return held


@dataclass
class ActionLog:
    """One run's chain of witnessed action bytes, and where it is written."""

    run_id: str
    path: Path | None = None
    chain: list[Witness] = field(default_factory=list)
    dropped: int = 0

    def head(self) -> str:
        """The link the next record points back at."""
        return self.chain[-1].link() if self.chain else GENESIS

    def records(self) -> list[dict]:
        return records(self.chain)

    def __len__(self) -> int:
        return len(self.chain)


def open_log(run_id: str, *, directory: str | Path | None = None,
             name: str = LOG_NAME) -> ActionLog:
    """Start a run's log. Without a directory the chain lives only in memory."""
    if not isinstance(run_id, str) or not run_id:
        raise WitnessError("a run's log is named by its run id")
    return ActionLog(run_id=run_id,
                     path=Path(directory) / name if directory is not None else None)


def _write(log: ActionLog, record: dict) -> bool:
    """Append one record. Never raises. A failed write is counted and reported."""
    if log.path is None:
        return True
    try:
        log.path.parent.mkdir(parents=True, exist_ok=True)
        with log.path.open("ab") as stream:
            stream.write(canonical_bytes(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except Exception as exc:  # noqa: BLE001 -- the action path must not break
        log.dropped += 1
        print(f"action-witness: record {len(log.chain) - 1} not written "
              f"(non-fatal, the log will read as broken): {exc}", file=sys.stderr)
        return False


def observe(log: ActionLog, data: object, *, action: str, kind: str, seq: int,
            encoding: str = "", spans: tuple[Span, ...] | list[Span] = (),
            observed_at: str = "", context: dict | None = None) -> Witness:
    """Witness one side of an action onto the log's chain.

    ``encoding`` says how the caller turned its value into these bytes, so a
    verifier can reproduce them. Empty means the bytes were already bytes.
    """
    witness = append(log.chain, data, label=f"{action}/{kind}",
                     observed_at=observed_at, spans=spans,
                     context=_context(log.run_id, action, kind, seq,
                                      encoding or "none", context))
    _write(log, witness.record())
    return witness


def _encoded(value: object) -> tuple[bytes, str]:
    """Bytes for a caller's value, and the name of how they were produced."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value), ""
    if isinstance(value, str):
        return value.encode(UTF8), UTF8
    return canonical_bytes(value), CANONICAL_JSON


def observe_action(log: ActionLog, *, action: str, seq: int, args: object,
                   output: object, observed_at: str = "",
                   context: dict | None = None) -> dict:
    """Witness both sides of one action and return what binds it to the chain.

    Bytes are witnessed as they are. Text is witnessed as UTF-8 and a JSON value
    as its canonical form, and the record says which, because a digest over
    bytes nobody can reproduce is a digest nobody can check.
    """
    args_bytes, args_encoding = _encoded(args)
    output_bytes, output_encoding = _encoded(output)
    first = observe(log, args_bytes, action=action, kind=INPUT, seq=seq,
                    encoding=args_encoding, observed_at=observed_at,
                    context=context)
    second = observe(log, output_bytes, action=action, kind=OUTPUT, seq=seq,
                     encoding=output_encoding, observed_at=observed_at,
                     context=context)
    return {"schema": ACTION_SCHEMA, "action": action, "seq": seq,
            "input": {"sha256": first.sha256, "bytes": first.length,
                      "encoding": args_encoding or "none"},
            "output": {"sha256": second.sha256, "bytes": second.length,
                       "encoding": output_encoding or "none"},
            "link": second.link()}


def read_log(path: str | Path) -> list:
    """The records in a log file, in order.

    A line that is not JSON is kept as None, so a corrupted line becomes an
    UNVERIFIABLE record rather than a silently shorter chain that still reads
    as intact.
    """
    held: list = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            held.append(json.loads(line))
        except ValueError:
            held.append(None)
    return held


def verify_log(source: str | Path | list, *, start: str = GENESIS,
               resolve=None) -> dict:
    """Check a run's log offline. Takes a path or the records themselves."""
    if isinstance(source, (str, Path)):
        try:
            source = read_log(source)
        except OSError as exc:
            result = verify_chain([], start=start)
            result["detail"] = f"the log could not be read: {exc}"
            return result
    return verify_chain(source, start=start, resolve=resolve)


def does_not_prove() -> list[str]:
    """What a run's action log leaves open. Never empty."""
    return byte_does_not_prove() + [
        "the log holds the actions this layer was told about, so an action "
        "taken around it leaves nothing behind to break a link",
        "the encoding names how the caller produced these bytes, which is the "
        "caller's word, and only re-encoding the same value tests it",
    ]

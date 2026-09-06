"""receipting_cost_bench.py -- what it costs to keep the receipt.

Every argument against writing the record down is a cost argument, and it is
usually made without a number. This measures the number on the path the
harness actually uses: `observe_action` against a real log, one action at a
time, on whatever filesystem the reader is standing on.

Three configurations of the same code, so the total can be attributed instead
of quoted whole.

    chain only   hash the bytes and link the record, nothing on disk
    buffered     the same path with the durability syscall removed
    durable      the path as it ships, one fsync per record

Subtracting them says where the time goes. On the machine this was written on,
hashing was cheap and writing was cheap, and waiting for the disk to admit it
holds the bytes was almost all of it.

The timings are one machine, one filesystem, one day, and they are reported
with the range across batches because a single figure would read as a
constant. What carries to another disk is the shape rather than the numbers:
the receipt is arithmetic and the durability is I/O, and only one of those
gets cheaper when the code gets better.
"""
from __future__ import annotations

import hashlib
import platform
import statistics
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from . import action_witness
from .action_witness import LOG_NAME, observe_action, open_log
from .byte_witness_verify import verify_chain
from .evidence_json import canonical_bytes

SCHEMA = "flywheel.receipting-cost/v1"

#: One recorded action, shaped like the ones the harness witnesses in earnest:
#: a tool call with a small argument object and a page of output. Two records
#: land per action, one for each side.
ACTION = "read_file"
ARGS = {"tool": "read_file", "path": "harness/lanes.py", "start": 1, "end": 120}
OUTPUT = "x" * 512
RECORDS_PER_ACTION = 2

BATCHES = 7
PER_BATCH = 25
DISK_ACTIONS = 50


class _NoSyncOs:
    """`os` as one module sees it, with the durability syscall taken out.

    Patching `os.fsync` itself would reach every module in the process, and a
    run happening elsewhere would quietly lose its durability while this arm is
    timed. This replaces the name a single module resolves, and puts it back.
    """

    def __init__(self, real) -> None:
        self._real = real

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def fsync(self, fd: int) -> None:
        return None


def _actions(log, count: int) -> None:
    for seq in range(count):
        observe_action(log, action=ACTION, seq=seq, args=ARGS, output=OUTPUT)


@contextmanager
def _chain_only(index: int) -> Iterator[Any]:
    """A log with no file behind it. Hashing and linking, nothing else."""
    yield open_log(f"cost-{index}")


@contextmanager
def _durable(index: int) -> Iterator[Any]:
    """The path as it ships."""
    with tempfile.TemporaryDirectory() as tmp:
        yield open_log(f"cost-{index}", directory=tmp)


@contextmanager
def _buffered(index: int) -> Iterator[Any]:
    """The shipping path minus fsync, to attribute the wait to the wait."""
    real = action_witness.os
    action_witness.os = _NoSyncOs(real)
    try:
        with _durable(index) as log:
            yield log
    finally:
        action_witness.os = real


def _microseconds_per_action(arm: Callable[[int], Any], batches: int,
                             per_batch: int) -> list[float]:
    """One figure per batch, so the spread is visible rather than averaged off.

    Each batch opens its own log. A chain that kept growing across batches
    would be measuring its length as well as its cost.
    """
    figures = []
    for index in range(batches):
        with arm(index) as log:
            started = time.perf_counter()
            _actions(log, per_batch)
            elapsed = time.perf_counter() - started
        figures.append(elapsed / per_batch * 1e6)
    return figures


def _spread(figures: list[float]) -> dict[str, float]:
    return {"median_us": round(statistics.median(figures), 1),
            "low_us": round(min(figures), 1),
            "high_us": round(max(figures), 1)}


def _known_bytes() -> dict[str, bytes]:
    """Digest to bytes for the two payloads every action in here carries."""
    known = {}
    for value in (ARGS, OUTPUT):
        raw = (value.encode("utf-8") if isinstance(value, str)
               else canonical_bytes(value))
        known[hashlib.sha256(raw).hexdigest()] = raw
    return known


def _on_disk(count: int = DISK_ACTIONS) -> dict[str, Any]:
    """What the log weighs, and what rechecking it costs.

    The resolver is a two-entry map because every action here carries the same
    payload. That is the cheapest case a verifier can be handed, and a real
    transcript read off disk costs more than this.
    """
    known = _known_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        log = open_log("cost-disk", directory=tmp)
        _actions(log, count)
        size = (Path(tmp) / LOG_NAME).stat().st_size
        records = log.records()
    started = time.perf_counter()
    result = verify_chain(records, resolve=known.__getitem__)
    seconds = time.perf_counter() - started
    checked = max(result["checked"], 1)
    return {"actions": count, "records_checked": result["checked"],
            "verdict": result["verdict"], "log_bytes": size,
            "bytes_per_action": round(size / count, 1),
            "verify_us_per_record": round(seconds / checked * 1e6, 1)}


def _share(waiting: float, total: float) -> float | None:
    """How much of the total the fsync took, or nothing when it cannot be said.

    The three arms are timed separately, so this difference is a difference of
    medians rather than a duration anybody measured. On a small sample or a
    busy host the durable arm can come out no slower than the buffered one, and
    a Windows runner produced exactly that. Reporting None says the run did not
    separate them. Clamping to zero would instead report that durability is
    free, which is a claim this never made and the data does not support.
    """
    if total <= 0 or waiting <= 0:
        return None
    return round(waiting / total, 4)


def _reading(waiting: float, total: float) -> str:
    """One sentence a reader can act on, taken from what was measured."""
    if waiting <= 0:
        return ("the arms did not separate on this run: the durable arm was no "
                "slower than the buffered one, so this sample says nothing "
                "about what the fsync costs. A larger sample or a quieter host "
                "is what would answer it")
    if total and waiting / total >= 0.5:
        return ("the record is arithmetic and the durability is a syscall. "
                "Most of what a witnessed action costs here is the wait for "
                "one fsync, so batching the flush is the lever, and it is paid "
                "for in the size of the crash window")
    return ("the wait for durability is not the larger part of this cost on "
            "this filesystem, so hashing and writing the record are what a "
            "faster path would have to improve")


def run_receipting_cost_benchmark(batches: int = BATCHES,
                                  per_batch: int = PER_BATCH) -> dict[str, Any]:
    """Measure the three arms and attribute the total between them."""
    chain = _spread(_microseconds_per_action(_chain_only, batches, per_batch))
    buffered = _spread(_microseconds_per_action(_buffered, batches, per_batch))
    durable = _spread(_microseconds_per_action(_durable, batches, per_batch))
    hashing = chain["median_us"]
    writing = round(buffered["median_us"] - hashing, 1)
    waiting = round(durable["median_us"] - buffered["median_us"], 1)
    total = durable["median_us"]
    return {
        "schema": SCHEMA,
        "denominator": {"batches": batches, "actions_per_batch": per_batch,
                        "records_per_action": RECORDS_PER_ACTION,
                        "payload_bytes": len(canonical_bytes(ARGS)) + len(OUTPUT)},
        "platform": {"system": platform.system(),
                     "python": platform.python_version()},
        "arms": {"chain_only": chain, "buffered": buffered, "durable": durable},
        "attribution": {"hash_and_link_us": hashing, "write_us": writing,
                        "wait_for_durability_us": waiting, "total_us": total,
                        "durability_share": _share(waiting, total)},
        "disk": _on_disk(),
        "reading": _reading(waiting, total),
        "does_not_prove": does_not_prove(),
    }


def does_not_prove() -> list[str]:
    """What this measurement leaves open. Never empty."""
    return [
        "the timings are one machine, one filesystem and one run, and an "
        "encrypted, networked or virtualised disk answers fsync differently",
        "a drive that reports a flush it has not completed returns faster and "
        "keeps less, and nothing here can tell the two apart",
        "it measures the cost of writing the record, not the cost of the "
        "action worth recording, so an action that takes a second is barely "
        "moved by any figure here",
        "every action carries the same payload, so hashing runs on warm cache "
        "lines and the verifier's resolver is a two-entry map",
        "the buffered arm is the shipping path with one syscall removed, which "
        "is an attribution of the cost rather than a configuration anyone runs",
    ]

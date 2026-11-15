"""blocks.py -- load an authored block set from a directory of JSON records.

The repository ships authored records as one JSON file per record, and until now
nothing read them: every caller built its pool in memory or through a backend.
A server that serves the authored set needs a loader, and it lives here rather
than in the MCP layer so a build script or a test can call it with no transport
around it.

A file that does not parse or does not validate is reported, never skipped in
silence. A pool that quietly drops the record someone just wrote is worse than
one that refuses to load: the drop looks like success.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from canon.schema import Record
from canon.validator import validate_record

ENV_BLOCKS_DIR = "CANON_BLOCKS_DIR"


@dataclass(frozen=True, slots=True)
class BlockLoad:
    """What a directory yielded: the records that loaded, and one problem string
    per file that did not.

    `directory` is the path that was read, or None when no directory was found
    at all. Those are different facts: a configured directory holding nothing is
    an empty authored set, while no directory at all is an unconfigured server.
    `ok` is True only when a directory was read and every file in it loaded, so
    a partial load never reads as a clean one.
    """

    directory: str | None
    records: tuple[Record, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.directory is not None and not self.problems


def default_blocks_dir() -> str | None:
    """`CANON_BLOCKS_DIR` when set, else this checkout's own `blocks/`.

    An installed package has no sibling `blocks/` directory, and this returns
    None there rather than inventing a path that does not exist. The env
    variable is the only way to point a server at an authored set somewhere
    else, so the location is operator configuration and never tool input.
    """
    env = os.environ.get(ENV_BLOCKS_DIR)
    if env:
        return env
    candidate = Path(__file__).resolve().parents[2] / "blocks"
    return str(candidate) if candidate.is_dir() else None


def load_blocks(directory: str | None = None) -> BlockLoad:
    """Read every `*.json` in `directory` (default: `default_blocks_dir()`) into
    a validated Record.

    Files are read in sorted name order so a rebuild from the same directory
    yields the same pool order; canon's own ordering is the clock-free ordinal,
    and this only keeps the loader from adding filesystem order as a second,
    unstable one. Total: a parse failure, a schema mismatch, and a semantic
    problem all land in `problems` rather than raising.
    """
    target = directory if directory is not None else default_blocks_dir()
    if target is None:
        return BlockLoad(None, (), (f"no blocks directory; set {ENV_BLOCKS_DIR}",))
    path = Path(target)
    if not path.is_dir():
        return BlockLoad(None, (), (f"not a directory: {target}",))
    records: list[Record] = []
    problems: list[str] = []
    for entry in sorted(path.glob("*.json")):
        rec, problem = _load_one(entry)
        if rec is None:
            problems.append(problem)
        else:
            records.append(rec)
    return BlockLoad(str(path), tuple(records), tuple(problems))


def _load_one(entry: Path) -> tuple[Record | None, str]:
    """One file to one record, or None and the reason it did not load."""
    try:
        raw = json.loads(entry.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{entry.name}: {type(exc).__name__}: {exc}"
    try:
        rec = Record.from_dict(raw)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return None, f"{entry.name}: {type(exc).__name__}: {exc}"
    bad = validate_record(rec)
    if bad:
        return None, f"{entry.name}: {'; '.join(bad)}"
    return rec, ""

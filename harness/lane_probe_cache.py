"""What the last lane probe found, kept across polls and engine restarts.

The desktop polls ``GET /api/lanes`` every few seconds without probing, and a
poll used to erase what a probe had found (D1). This cache keeps each lane's
last probe outcome in ``<home>/state/lane-probes.json``:

- a record counts only for the engine version and lane pin it was taken under,
  so an upgrade or a new pin reads "not checked" instead of an old answer;
- a record from an earlier engine session is served with its time and marked
  stale ("Last checked <time>") until a probe in this session replaces it;
- a lane call that could not launch rewrites the lane's record at once;
- a key name bound to a call that succeeded, to a tool that spends it, is
  recorded as validated (lane_call_route);
- a file that cannot be written (another engine holding it, a sharing
  violation) is logged, and the records stay in memory for this process.

The start probe runs only when the engine starts with ``--desktop-launch``,
never under ``flywheel up`` or in gateway tests: four lanes at a time, 20
seconds each, and no http lane unless network contact at start is allowed
(O-10; the default is on request only).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .lane_workdir import flywheel_home

SCHEMA = "flywheel.lane-probes/v1"
CACHE_FILE = "lane-probes.json"
START_WORKERS = 4
START_TIMEOUT_S = 20
OUTCOMES = ("answered", "unhealthy", "cannot_launch", "unreachable")
_SLUG = re.compile(r"[a-z0-9_]{1,64}\Z")
_PROBE_CODE = re.compile(r"MCP probe failed: ([a-z0-9_]{1,64}) \(cannot launch\)")
_LOG = logging.getLogger(__name__)
DESKTOP_FLAG_HELP = "started by Flywheel Desktop: check the lanes once in the background"


def add_desktop_flag(parser) -> None:
    """The gateway's ``--desktop-launch`` flag (a one-line hook in gateway.py)."""
    parser.add_argument("--desktop-launch", action="store_true", help=DESKTOP_FLAG_HELP)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def engine_version() -> str:
    """The installed engine version the cache keys on; 'unknown' when unread."""
    from importlib import metadata
    try:
        return metadata.version("flywheel-verify")
    except metadata.PackageNotFoundError:
        return "unknown"


def slug(value: object, fallback: str) -> str:
    """``value`` when it is a closed-set slug, else ``fallback``."""
    return value if isinstance(value, str) and _SLUG.fullmatch(value) else fallback


def outcome_from_row(row: Mapping[str, object], *, http: bool) -> tuple[str, str] | None:
    """(outcome, code) from a probed ``lanes.lane_status`` row, or None when the
    row reports no probe (runtime selection failed, or not probed)."""
    status, detail = row.get("status"), str(row.get("detail", ""))
    if status == "live":
        return "answered", ""
    if status == "stale":
        return "unhealthy", "health_check_failed"
    match = _PROBE_CODE.search(detail)
    if match is None:
        return None
    return ("unreachable", "network_error") if http else ("cannot_launch", match.group(1))


class ProbeCache:
    """The probe records of one Flywheel home. Thread-safe; one per home."""

    def __init__(self, path: Path, *, engine: str | None = None,
                 clock: Callable[[], str] = utc_now) -> None:
        self.path = Path(path)
        self.engine = engine_version() if engine is None else engine
        self.clock = clock
        self._fresh: set[str] = set()
        self._lock = threading.Lock()
        self._memory: dict | None = None   # set while the file cannot be written

    def _load(self) -> dict:
        if self._memory is not None:
            return json.loads(json.dumps(self._memory))
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            data = {}
        rows = data.get("rows") if isinstance(data.get("rows"), dict) else {}
        keys = data.get("validated") if isinstance(data.get("validated"), dict) else {}
        return {"schema": SCHEMA, "rows": rows, "validated": keys}

    def _save(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as error:
            _LOG.warning("lane probe cache: could not write %s (%s); keeping the "
                         "records in memory", self.path, type(error).__name__)
            self._memory = json.loads(json.dumps(data))
            return
        self._memory = None

    def lookup(self, lane: str, pin: str) -> tuple[dict | None, bool]:
        """(record, fresh): the record taken under this engine and pin, and
        whether a probe in this engine session wrote it."""
        with self._lock:
            record = self._load()["rows"].get(lane)
            fresh = lane in self._fresh
        if (not isinstance(record, dict) or record.get("engine") != self.engine
                or record.get("pin") != pin or record.get("outcome") not in OUTCOMES):
            return None, False
        return dict(record), fresh

    def record(self, lane: str, pin: str, outcome: str, *, code: str = "",
               tools: Iterable[str] = ()) -> dict:
        """Write one lane's outcome now and mark it fresh for this session."""
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown probe outcome {outcome!r}")
        record = {"engine": self.engine, "pin": pin, "checked_at": self.clock(),
                  "outcome": outcome, "code": slug(code, "") if code else "",
                  "tools": sorted({str(name) for name in tools})}
        with self._lock:
            data = self._load()
            data["rows"][lane] = record
            self._save(data)
            self._fresh.add(lane)
        return dict(record)

    def record_row(self, lane: str, pin: str, row: Mapping[str, object], *,
                   http: bool) -> dict | None:
        """Record a probed roster row; None when the row holds no probe."""
        found = outcome_from_row(row, http=http)
        if found is None:
            return None
        names = row.get("tool_names") or ()
        return self.record(lane, pin, found[0], code=found[1],
                           tools=names if isinstance(names, (list, tuple)) else ())

    def record_failure(self, lane: str, pin: str, code: str) -> dict:
        """A lane call that could not launch rewrites the row (H-10)."""
        return self.record(lane, pin, "cannot_launch", code=slug(code, "launch_failed"))

    def record_validated(self, lane: str, names: Iterable[str]) -> None:
        """Key names bound to a lane call that succeeded. Names only."""
        with self._lock:
            data = self._load()
            kept = set(data["validated"].get(lane) or ()) | {str(n) for n in names}
            data["validated"][lane] = sorted(kept)
            self._save(data)

    def validated(self, lane: str) -> set[str]:
        with self._lock:
            return set(self._load()["validated"].get(lane) or ())


_CACHES: dict[str, ProbeCache] = {}
_CACHES_LOCK = threading.Lock()


def default_cache(environ: Mapping[str, str] | None = None) -> ProbeCache:
    """The cache of the current Flywheel home, one instance per home."""
    path = flywheel_home(os.environ if environ is None else environ) / "state" / CACHE_FILE
    with _CACHES_LOCK:
        return _CACHES.setdefault(str(path), ProbeCache(path))


def lane_pin(name: str) -> str:
    from .lanes_registry import LANES
    lane = LANES.get(name)
    return lane.version if lane is not None else ""


def probe_lanes(names: Iterable[str], *, cache: ProbeCache,
                status_fn: Callable[..., dict] | None = None,
                workers: int = START_WORKERS,
                timeout: float = START_TIMEOUT_S) -> dict[str, dict]:
    """Probe ``names`` ``workers`` at a time and record each outcome."""
    from .lanes_registry import LANES
    if status_fn is None:
        from .lanes import lane_status as status_fn

    def _one(name: str) -> tuple[str, dict]:
        try:
            row = status_fn(name, probe=True, timeout=timeout)
        except Exception as error:  # one lane's defect must not stop the others
            print(f"lane probe: {name}: {type(error).__name__}", file=sys.stderr)
            return name, {"name": name, "status": "declared", "detail": "probe raised"}
        cache.record_row(name, lane_pin(name), row, http=LANES[name].kind == "http")
        return name, row

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return dict(pool.map(_one, [n for n in names if n in LANES]))


def start_probe(*, desktop_launch: bool, cache: ProbeCache | None = None,
                status_fn: Callable[..., dict] | None = None,
                allow_network: bool = False,
                background: bool = True) -> threading.Thread | dict | None:
    """The start probe. Nothing runs unless the desktop started the engine."""
    if not desktop_launch:
        return None
    from .lanes_registry import LANES
    names = [n for n, lane in LANES.items() if allow_network or lane.kind != "http"]
    target = cache or default_cache()

    def _run() -> dict:
        return probe_lanes(names, cache=target, status_fn=status_fn)

    if not background:
        return _run()
    thread = threading.Thread(target=_run, name="flywheel-lane-start-probe", daemon=True)
    thread.start()
    return thread

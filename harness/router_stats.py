"""router_stats.py — persisted per-provider stats for cost/quality-aware routing.

Routing decisions only: which provider to TRY, and in what order. The accept
authority stays the oracle, so no learned model touches the accept path. A
cost/success-ordered cascade provably dominates a fixed-order one when a decent
quality estimator is available (Cascade Routing, arXiv 2410.10347), and a plain
frequency table is a sufficient estimator -- no neural net. Persisted as JSON so
the ordering survives restarts and a stranger can audit why a provider was picked.

- record(endpoint, ok, latency): update the table after each attempt.
- order(chain): reorder a failover chain best-first, circuit-open providers last.
- is_circuit_open(endpoint): skip a provider on a run of consecutive failures.
- snapshot(): the whole table, re-derivable.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory


class RouterStatsError(RuntimeError):
    """Fixed, host-detail-free failure for durable stats writes."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class ProviderStat:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def mean_latency(self) -> float:
        return self.total_latency / self.attempts if self.attempts else 0.0


class RouterStats:
    """A frequency table over provider outcomes. `cost` (endpoint -> relative price)
    is optional; when absent every provider costs 1, so ordering is by quality."""

    def __init__(self, path=None, *, cost: "dict | None" = None,
                 circuit_threshold: int = 3, lock_timeout_s: float = 2.0):
        self.path = Path(path) if path else None
        self.cost = dict(cost or {})
        self.circuit_threshold = circuit_threshold
        self.lock_timeout_s = lock_timeout_s
        self.stats: "dict[str, ProviderStat]" = {}
        # the gateway serves via ThreadingHTTPServer, so record() runs
        # concurrently from request threads: guard the table and the write
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        if not self.path:
            return
        try:
            with ExclusiveJourneyLock.acquire(self._lock_path(), self.lock_timeout_s):
                self._load_unlocked()
        except JourneyLockBusy:
            raise RouterStatsError("STORE_BUSY") from None
        except RouterStatsError:
            raise
        except (OSError, ValueError, TypeError):
            raise RouterStatsError("STORE_COMMIT_FAILED") from None

    def _load_unlocked(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # a truncated / interleaved file must not be fatal: quarantine it
            # and start clean rather than crashing every route from then on
            self.stats = {}
            try:
                self.path.replace(self.path.with_suffix(".corrupt"))
            except OSError:
                pass
            return
        loaded = {}
        for name, d in (raw.get("providers") or {}).items():
            loaded[name] = ProviderStat(**{
                k: d[k] for k in ProviderStat.__dataclass_fields__ if k in d})
        self.stats = loaded

    def _lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.lock")

    def _retry_windows_permission(self, deadline: float) -> None:
        if os.name != "nt" or time.monotonic() >= deadline:
            raise RouterStatsError("STORE_BUSY") from None
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def _replace_with_retry(self, source: Path) -> None:
        deadline = time.monotonic() + max(0.0, self.lock_timeout_s)
        while True:
            try:
                os.replace(source, self.path)
                return
            except PermissionError:
                self._retry_windows_permission(deadline)

    def _fsync_file_with_retry(self, path: Path) -> None:
        deadline = time.monotonic() + max(0.0, self.lock_timeout_s)
        while True:
            try:
                with path.open("r+b") as stream:
                    os.fsync(stream.fileno())
                return
            except PermissionError:
                self._retry_windows_permission(deadline)

    def _save(self, stats: "dict[str, ProviderStat] | None" = None) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # atomic: write a temp file then os.replace, so a concurrent reader or
        # a crash mid-write never sees a torn stats file
        tmp = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.{uuid4().hex}.tmp")
        try:
            with tmp.open("xb") as stream:
                stream.write(json.dumps(
                    self._snapshot_from(self.stats if stats is None else stats),
                    sort_keys=True,
                ).encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            self._replace_with_retry(tmp)
            self._fsync_file_with_retry(self.path)
            fsync_directory(self.path.parent)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _copy_stats(stats: "dict[str, ProviderStat]") -> "dict[str, ProviderStat]":
        return {
            endpoint: ProviderStat(**{
                field: getattr(stat, field)
                for field in ProviderStat.__dataclass_fields__
            })
            for endpoint, stat in stats.items()
        }

    @staticmethod
    def _record_in(stats: "dict[str, ProviderStat]", endpoint: str,
                   ok: bool, latency: float) -> None:
        s = stats.setdefault(endpoint, ProviderStat())
        s.attempts += 1
        s.total_latency += max(0.0, latency)
        if ok:
            s.successes += 1
            s.consecutive_failures = 0
        else:
            s.failures += 1
            s.consecutive_failures += 1

    def _reload_after_failed_save(self) -> None:
        if self.path and self.path.exists():
            self._load_unlocked()
        else:
            self.stats = {}

    def record(self, endpoint: str, ok: bool, latency: float = 0.0) -> None:
        with self._lock:
            if not self.path:
                self._record_in(self.stats, endpoint, ok, latency)
                return
            try:
                with ExclusiveJourneyLock.acquire(self._lock_path(), self.lock_timeout_s):
                    if self.path.exists():
                        self._load_unlocked()
                    staged = self._copy_stats(self.stats)
                    self._record_in(staged, endpoint, ok, latency)
                    try:
                        self._save(staged)
                    except (RouterStatsError, OSError, ValueError, TypeError):
                        self._reload_after_failed_save()
                        raise
                    self.stats = staged
            except JourneyLockBusy:
                raise RouterStatsError("STORE_BUSY") from None
            except RouterStatsError:
                raise
            except (OSError, ValueError, TypeError):
                raise RouterStatsError("STORE_COMMIT_FAILED") from None

    def _score_from(self, endpoint: str, stats: "dict[str, ProviderStat]") -> float:
        s = stats.get(endpoint)
        if s is None or s.attempts == 0:
            base = 1.0
        else:
            total = sum(x.attempts for x in stats.values()) or 1
            z = 1.96
            n = s.attempts
            p = s.success_rate
            denom = 1 + z * z / n
            centre = p + z * z / (2 * n)
            margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
            lb = (centre - margin) / denom
            bonus = 0.15 * math.sqrt(math.log(total + 1) / n)
            base = min(1.0, lb) + bonus
        cost = self.cost.get(endpoint, 1.0) or 1.0
        return base / cost

    def score(self, endpoint: str) -> float:
        """Higher is better. The quality term is the WILSON LOWER BOUND of the
        success rate, not the raw rate, so thin evidence (one minted success)
        cannot leap ahead of a long track record: the bound is wide when n is
        small and tightens as attempts accrue. An exploration bonus that decays
        with attempts keeps an unseen provider tried optimistically. Pure
        arithmetic, no learned model. Divided by relative cost."""
        return self._score_from(endpoint, self.stats)

    def is_circuit_open(self, endpoint: str) -> bool:
        s = self.stats.get(endpoint)
        return bool(s and s.consecutive_failures >= self.circuit_threshold)

    def order(self, endpoints: list) -> list:
        """Best-first failover order: healthy providers by score descending, then
        any circuit-open ones last (still tried if every healthy provider fails)."""
        healthy = [e for e in endpoints if not self.is_circuit_open(e)]
        tripped = [e for e in endpoints if self.is_circuit_open(e)]
        healthy.sort(key=lambda e: -self.score(e))
        return healthy + tripped

    def _snapshot_from(self, stats: "dict[str, ProviderStat]") -> dict:
        return {
            "schema": "flywheel.router-stats/v1",
            "circuit_threshold": self.circuit_threshold,
            "providers": {
                e: {**asdict(s), "success_rate": round(s.success_rate, 4),
                    "mean_latency": round(s.mean_latency, 4),
                    "circuit_open": s.consecutive_failures >= self.circuit_threshold,
                    "score": round(self._score_from(e, stats), 4)}
                for e, s in sorted(stats.items())},
        }

    def snapshot(self) -> dict:
        return self._snapshot_from(self.stats)

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
from dataclasses import asdict, dataclass
from pathlib import Path


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
                 circuit_threshold: int = 3):
        self.path = Path(path) if path else None
        self.cost = dict(cost or {})
        self.circuit_threshold = circuit_threshold
        self.stats: "dict[str, ProviderStat]" = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for name, d in (raw.get("providers") or {}).items():
            self.stats[name] = ProviderStat(**{k: d[k] for k in ProviderStat.__dataclass_fields__ if k in d})

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.snapshot(), sort_keys=True), encoding="utf-8")

    def record(self, endpoint: str, ok: bool, latency: float = 0.0) -> None:
        s = self.stats.setdefault(endpoint, ProviderStat())
        s.attempts += 1
        s.total_latency += max(0.0, latency)
        if ok:
            s.successes += 1
            s.consecutive_failures = 0
        else:
            s.failures += 1
            s.consecutive_failures += 1
        self._save()

    def score(self, endpoint: str) -> float:
        """Higher is better. UCB-lite: success rate plus an exploration bonus that
        decays with attempts (so an unseen provider is tried optimistically), all
        divided by relative cost. Pure arithmetic, no learned model."""
        s = self.stats.get(endpoint)
        if s is None or s.attempts == 0:
            base = 1.0                                   # optimistic prior for the unseen
        else:
            total = sum(x.attempts for x in self.stats.values()) or 1
            base = s.success_rate + math.sqrt(2 * math.log(total) / s.attempts)
        cost = self.cost.get(endpoint, 1.0) or 1.0
        return base / cost

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

    def snapshot(self) -> dict:
        return {
            "schema": "flywheel.router-stats/v1",
            "circuit_threshold": self.circuit_threshold,
            "providers": {
                e: {**asdict(s), "success_rate": round(s.success_rate, 4),
                    "mean_latency": round(s.mean_latency, 4),
                    "circuit_open": self.is_circuit_open(e),
                    "score": round(self.score(e), 4)}
                for e, s in sorted(self.stats.items())},
        }

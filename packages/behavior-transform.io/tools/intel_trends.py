"""Trend analytics over the provider intelligence store.

Time-windowed analysis of success rates, friction trends, per-level
effectiveness, and trigger term frequency. Builds on the raw event
stream in provider_intelligence.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from provider_intelligence import IntelStore, IntelEvent, intel_store


@dataclass
class TrendWindow:
    """Analytics for a specific time window."""
    window_seconds: float
    event_count: int
    success_rate: float
    friction_rate: float
    avg_quality: float
    avg_level: float
    top_triggers: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_seconds": self.window_seconds,
            "event_count": self.event_count,
            "success_rate": round(self.success_rate, 4),
            "friction_rate": round(self.friction_rate, 4),
            "avg_quality": round(self.avg_quality, 3),
            "avg_level": round(self.avg_level, 2),
            "top_triggers": self.top_triggers[:10],
        }


@dataclass
class LevelEffectiveness:
    """Per-level success metrics."""
    level: int
    attempts: int
    successes: int
    success_rate: float
    avg_quality: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "attempts": self.attempts,
            "successes": self.successes,
            "success_rate": round(self.success_rate, 4),
            "avg_quality": round(self.avg_quality, 3),
        }


@dataclass
class TrendDirection:
    """Whether a metric is improving, declining, or stable."""
    metric: str
    direction: str  # improving, declining, stable
    recent_value: float
    historical_value: float
    delta: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "direction": self.direction,
            "recent": round(self.recent_value, 4),
            "historical": round(self.historical_value, 4),
            "delta": round(self.delta, 4),
        }


@dataclass
class TrendReport:
    """Full trend analysis report."""
    total_events: int
    windows: list[TrendWindow] = field(default_factory=list)
    level_effectiveness: list[LevelEffectiveness] = field(default_factory=list)
    trends: list[TrendDirection] = field(default_factory=list)
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "provider": self.provider,
            "windows": [w.to_dict() for w in self.windows],
            "level_effectiveness": [l.to_dict() for l in self.level_effectiveness],
            "trends": [t.to_dict() for t in self.trends],
        }

    def summary(self) -> str:
        lines = [f"Trend Report ({self.provider or 'all providers'})"]
        lines.append(f"  Total events: {self.total_events}")
        if self.windows:
            latest = self.windows[0]
            lines.append(
                f"  Latest window ({latest.event_count} events): "
                f"success={latest.success_rate:.0%} "
                f"friction={latest.friction_rate:.0%} "
                f"quality={latest.avg_quality:.2f}"
            )
        for t in self.trends:
            arrow = {"improving": "+", "declining": "-", "stable": "="}
            lines.append(
                f"  [{arrow.get(t.direction, '?')}] {t.metric}: "
                f"{t.historical_value:.0%} -> {t.recent_value:.0%}"
            )
        if self.level_effectiveness:
            lines.append("  Level effectiveness:")
            for le in self.level_effectiveness:
                if le.attempts > 0:
                    lines.append(
                        f"    L{le.level}: {le.success_rate:.0%} "
                        f"({le.successes}/{le.attempts})"
                    )
        return "\n".join(lines)


def _window_stats(events: list[IntelEvent]) -> TrendWindow:
    if not events:
        return TrendWindow(
            window_seconds=0, event_count=0,
            success_rate=0, friction_rate=0,
            avg_quality=0, avg_level=0,
        )
    n = len(events)
    successes = sum(1 for e in events if e.outcome == "success")
    friction = sum(
        1 for e in events
        if e.outcome in ("soft_refusal", "hard_refusal", "hedged")
    )
    trigger_counts: dict[str, int] = {}
    for e in events:
        for t in e.trigger_terms:
            trigger_counts[t] = trigger_counts.get(t, 0) + 1
    top = sorted(trigger_counts.items(), key=lambda x: -x[1])
    ts_range = events[-1].timestamp - events[0].timestamp if n > 1 else 0
    return TrendWindow(
        window_seconds=ts_range,
        event_count=n,
        success_rate=successes / n,
        friction_rate=friction / n,
        avg_quality=sum(e.quality_score for e in events) / n,
        avg_level=sum(e.modulation_level for e in events) / n,
        top_triggers=top[:10],
    )


def _level_stats(events: list[IntelEvent]) -> list[LevelEffectiveness]:
    buckets: dict[int, list[IntelEvent]] = {}
    for e in events:
        buckets.setdefault(e.modulation_level, []).append(e)
    result = []
    for level in sorted(buckets):
        evts = buckets[level]
        successes = sum(1 for e in evts if e.outcome == "success")
        result.append(LevelEffectiveness(
            level=level,
            attempts=len(evts),
            successes=successes,
            success_rate=successes / len(evts) if evts else 0,
            avg_quality=sum(e.quality_score for e in evts) / len(evts),
        ))
    return result


def _compute_trends(
    recent: list[IntelEvent], historical: list[IntelEvent],
) -> list[TrendDirection]:
    if not recent or not historical:
        return []
    trends = []
    for metric, extractor in [
        ("success_rate", lambda evts: sum(
            1 for e in evts if e.outcome == "success"
        ) / len(evts) if evts else 0),
        ("friction_rate", lambda evts: sum(
            1 for e in evts
            if e.outcome in ("soft_refusal", "hard_refusal", "hedged")
        ) / len(evts) if evts else 0),
        ("avg_quality", lambda evts: sum(
            e.quality_score for e in evts
        ) / len(evts) if evts else 0),
    ]:
        r_val = extractor(recent)
        h_val = extractor(historical)
        delta = r_val - h_val
        threshold = 0.05
        if metric == "friction_rate":
            direction = (
                "improving" if delta < -threshold
                else "declining" if delta > threshold
                else "stable"
            )
        else:
            direction = (
                "improving" if delta > threshold
                else "declining" if delta < -threshold
                else "stable"
            )
        trends.append(TrendDirection(
            metric=metric, direction=direction,
            recent_value=r_val, historical_value=h_val, delta=delta,
        ))
    return trends


def analyze_trends(
    provider: str = "",
    store: IntelStore | None = None,
    recent_fraction: float = 0.3,
) -> TrendReport:
    """Analyze trends in the intelligence store.

    Args:
        provider: filter to a specific provider, or "" for all
        store: optional store override (defaults to global singleton)
        recent_fraction: fraction of events considered "recent" for trends
    """
    s = store or intel_store()
    all_events = s.load_events()
    if provider:
        all_events = [e for e in all_events if e.provider == provider]

    if not all_events:
        return TrendReport(total_events=0, provider=provider)

    all_events.sort(key=lambda e: e.timestamp)
    n = len(all_events)
    split = max(1, int(n * (1 - recent_fraction)))
    historical = all_events[:split]
    recent = all_events[split:]

    windows = [
        _window_stats(recent),
        _window_stats(all_events),
    ]
    levels = _level_stats(all_events)
    trends = _compute_trends(recent, historical)

    return TrendReport(
        total_events=n,
        provider=provider,
        windows=windows,
        level_effectiveness=levels,
        trends=trends,
    )


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="intel-trends",
        description="Trend analytics over the provider intelligence store",
    )
    parser.add_argument(
        "--provider", default="", help="Filter to a specific provider",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    report = analyze_trends(provider=args.provider)

    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(report.summary() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

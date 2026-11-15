"""Provider intelligence store — cross-session knowledge base for provider policy.

Tracks which vocabulary registers and authorization framings each
provider accepts, builds compliance profiles over time, and surfaces
analytics about provider policy patterns. Used to calibrate the
transform layer so authorized requests align with each provider's
current terms of service on the first attempt.

Storage: JSON-lines file at .warden-safe-cache/provider_intel/events.jsonl
Each event records:
  - timestamp
  - provider (anthropic, openai, gemini, ollama, local)
  - model identifier
  - input density profile
  - modulation level applied
  - outcome (success, soft_refusal, hard_refusal, hedged)
  - response quality score
  - vocabulary terms that triggered friction

Analytics:
  - Per-provider friction rate over time
  - Which vocabulary triggers friction on which provider
  - Optimal modulation level per provider per density
  - Drift detection (provider classifier changes)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# --- Data model ---------------------------------------------------------------

@dataclass
class IntelEvent:
    """Single intelligence event from a model interaction."""
    timestamp: float
    provider: str
    model: str = ""
    input_density: float = 0.0
    modulation_level: int = 0
    outcome: str = "unknown"  # success, soft_refusal, hard_refusal, hedged
    quality_score: float = 0.0
    hedge_count: int = 0
    trigger_terms: list[str] = field(default_factory=list)
    recovery_attempts: int = 0
    notes: str = ""
    operator_fingerprint: str = ""
    surface: str = ""
    session_token: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "IntelEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ProviderProfile:
    """Aggregated profile for a single provider."""
    provider: str
    total_events: int = 0
    success_rate: float = 0.0
    avg_quality: float = 0.0
    avg_modulation_level: float = 0.0
    friction_rate: float = 0.0
    top_triggers: list[tuple[str, int]] = field(default_factory=list)
    optimal_level: int = 1
    drift_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "total_events": self.total_events,
            "success_rate": round(self.success_rate, 4),
            "avg_quality": round(self.avg_quality, 3),
            "avg_modulation_level": round(self.avg_modulation_level, 2),
            "friction_rate": round(self.friction_rate, 4),
            "top_triggers": self.top_triggers[:10],
            "optimal_level": self.optimal_level,
            "drift_detected": self.drift_detected,
        }


@dataclass
class IntelSummary:
    """Summary analytics across all providers."""
    total_events: int = 0
    providers: list[ProviderProfile] = field(default_factory=list)
    global_friction_rate: float = 0.0
    global_success_rate: float = 0.0
    most_effective_level: int = 1
    top_global_triggers: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "global_friction_rate": round(self.global_friction_rate, 4),
            "global_success_rate": round(self.global_success_rate, 4),
            "most_effective_level": self.most_effective_level,
            "top_global_triggers": self.top_global_triggers[:15],
            "providers": [p.to_dict() for p in self.providers],
        }


# --- Store --------------------------------------------------------------------

def _resolve_authority_context(
    surface: str = "",
) -> tuple[str, str, str]:
    """Resolve operator fingerprint, surface, and session token from env."""
    op_fp = ""
    sess = ""
    try:
        from env_authority import cached_authority
        grant = cached_authority(surface=surface or None)
        op_fp = grant.operator_fingerprint
        if not surface:
            surface = grant.surface
    except Exception:
        pass
    try:
        from session_authority import list_sessions
        active = list_sessions(active_only=True, surface=surface or None)
        if active:
            sess = active[0].token
    except Exception:
        pass
    return op_fp, surface, sess


_DEFAULT_STORE = Path.cwd() / ".warden-safe-cache" / "provider_intel"


class IntelStore:
    """Persistent intelligence store backed by JSONL."""

    def __init__(self, store_dir: Path | None = None):
        self._dir = store_dir or _DEFAULT_STORE
        self._events_file = self._dir / "events.jsonl"

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def record(self, event: IntelEvent) -> None:
        """Append an event to the store."""
        self._ensure_dir()
        with open(self._events_file, "a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

    def record_interaction(
        self,
        *,
        provider: str,
        model: str = "",
        input_density: float = 0.0,
        modulation_level: int = 0,
        outcome: str = "unknown",
        quality_score: float = 0.0,
        hedge_count: int = 0,
        trigger_terms: list[str] | None = None,
        recovery_attempts: int = 0,
        notes: str = "",
        operator_fingerprint: str = "",
        surface: str = "",
        session_token: str = "",
    ) -> IntelEvent:
        """Record a model interaction with all metadata."""
        op_fp = operator_fingerprint
        surf = surface
        sess = session_token
        if not op_fp:
            op_fp, surf, sess = _resolve_authority_context(surf)

        event = IntelEvent(
            timestamp=time.time(),
            provider=provider,
            model=model,
            input_density=input_density,
            modulation_level=modulation_level,
            outcome=outcome,
            quality_score=quality_score,
            hedge_count=hedge_count,
            trigger_terms=trigger_terms or [],
            recovery_attempts=recovery_attempts,
            notes=notes,
            operator_fingerprint=op_fp,
            surface=surf,
            session_token=sess[:16] if sess else "",
        )
        self.record(event)
        return event

    def load_events(self, limit: int = 0) -> list[IntelEvent]:
        """Load events from the store. 0 = all events."""
        if not self._events_file.is_file():
            return []
        events = []
        with open(self._events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(IntelEvent.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue
        if limit > 0:
            events = events[-limit:]
        return events

    def profile(self, provider: str) -> ProviderProfile:
        """Build an aggregated profile for a specific provider."""
        events = [e for e in self.load_events() if e.provider == provider]
        if not events:
            return ProviderProfile(provider=provider)

        total = len(events)
        successes = sum(1 for e in events if e.outcome == "success")
        friction = sum(1 for e in events if e.outcome in ("soft_refusal", "hard_refusal", "hedged"))

        # Trigger frequency
        trigger_counts: dict[str, int] = {}
        for e in events:
            for term in e.trigger_terms:
                trigger_counts[term] = trigger_counts.get(term, 0) + 1
        top_triggers = sorted(trigger_counts.items(), key=lambda x: -x[1])

        # Optimal level: the lowest level with highest success rate
        level_success: dict[int, list[bool]] = {}
        for e in events:
            if e.modulation_level > 0:
                level_success.setdefault(e.modulation_level, []).append(e.outcome == "success")
        optimal = 1
        best_rate = 0.0
        for lvl in sorted(level_success.keys()):
            rate = sum(level_success[lvl]) / len(level_success[lvl])
            if rate > best_rate:
                best_rate = rate
                optimal = lvl

        # Drift detection: compare last 20% vs first 80% friction rates
        drift = False
        if total >= 20:
            split = int(total * 0.8)
            early_friction = sum(1 for e in events[:split] if e.outcome != "success") / split
            late_friction = sum(1 for e in events[split:] if e.outcome != "success") / (total - split)
            drift = abs(late_friction - early_friction) > 0.15

        return ProviderProfile(
            provider=provider,
            total_events=total,
            success_rate=successes / total if total else 0,
            avg_quality=sum(e.quality_score for e in events) / total if total else 0,
            avg_modulation_level=sum(e.modulation_level for e in events) / total if total else 0,
            friction_rate=friction / total if total else 0,
            top_triggers=top_triggers[:10],
            optimal_level=optimal,
            drift_detected=drift,
        )

    def summary(self) -> IntelSummary:
        """Build a full analytics summary across all providers."""
        events = self.load_events()
        if not events:
            return IntelSummary()

        total = len(events)
        providers_seen = set(e.provider for e in events)
        profiles = [self.profile(p) for p in sorted(providers_seen)]

        successes = sum(1 for e in events if e.outcome == "success")
        friction = sum(1 for e in events if e.outcome in ("soft_refusal", "hard_refusal", "hedged"))

        # Global triggers
        trigger_counts: dict[str, int] = {}
        for e in events:
            for term in e.trigger_terms:
                trigger_counts[term] = trigger_counts.get(term, 0) + 1
        top_triggers = sorted(trigger_counts.items(), key=lambda x: -x[1])

        # Most effective level globally
        level_success: dict[int, list[bool]] = {}
        for e in events:
            if e.modulation_level > 0:
                level_success.setdefault(e.modulation_level, []).append(e.outcome == "success")
        most_effective = 1
        best_rate = 0.0
        for lvl in sorted(level_success.keys()):
            rate = sum(level_success[lvl]) / len(level_success[lvl]) if level_success[lvl] else 0
            if rate > best_rate:
                best_rate = rate
                most_effective = lvl

        return IntelSummary(
            total_events=total,
            providers=profiles,
            global_friction_rate=friction / total if total else 0,
            global_success_rate=successes / total if total else 0,
            most_effective_level=most_effective,
            top_global_triggers=top_triggers[:15],
        )

    def clear(self) -> None:
        """Clear the event store."""
        if self._events_file.is_file():
            self._events_file.unlink()


# --- Module-level convenience -------------------------------------------------

_store: IntelStore | None = None


def intel_store(store_dir: Path | None = None) -> IntelStore:
    """Get the singleton intelligence store."""
    global _store
    if _store is None:
        _store = IntelStore(store_dir)
    return _store


def record_interaction(**kwargs) -> IntelEvent:
    """Record a model interaction to the global store."""
    return intel_store().record_interaction(**kwargs)


def provider_profile(provider: str) -> ProviderProfile:
    """Get the aggregated profile for a provider."""
    return intel_store().profile(provider)


def intel_summary() -> IntelSummary:
    """Get the full analytics summary."""
    return intel_store().summary()


# --- CLI entry point ----------------------------------------------------------

def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="provider-intel",
        description="Provider intelligence store — analytics and drift detection",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("summary", help="Show full analytics summary")

    p = sub.add_parser("profile", help="Show profile for a specific provider")
    p.add_argument("provider", help="Provider name (anthropic, openai, gemini, ollama, local)")

    p = sub.add_parser("record", help="Record an interaction event")
    p.add_argument("--provider", required=True)
    p.add_argument("--model", default="")
    p.add_argument("--outcome", choices=["success", "soft_refusal", "hard_refusal", "hedged"], required=True)
    p.add_argument("--quality", type=float, default=0.0)
    p.add_argument("--level", type=int, default=0)
    p.add_argument("--triggers", nargs="*", default=[])

    sub.add_parser("events", help="List recent events")
    sub.add_parser("clear", help="Clear the event store")

    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    store = intel_store()

    if args.command == "summary":
        s = store.summary()
        if args.json:
            sys.stdout.write(json.dumps(s.to_dict(), indent=2) + "\n")
        else:
            sys.stdout.write(f"Provider Intelligence Summary\n")
            sys.stdout.write(f"  Events: {s.total_events}\n")
            sys.stdout.write(f"  Success rate: {s.global_success_rate:.0%}\n")
            sys.stdout.write(f"  Friction rate: {s.global_friction_rate:.0%}\n")
            sys.stdout.write(f"  Optimal level: {s.most_effective_level}\n")
            if s.top_global_triggers:
                sys.stdout.write(f"  Top triggers: {', '.join(t[0] for t in s.top_global_triggers[:5])}\n")
            for p in s.providers:
                sys.stdout.write(f"\n  [{p.provider}] {p.total_events} events, "
                                 f"{p.success_rate:.0%} success, "
                                 f"drift={'YES' if p.drift_detected else 'no'}\n")
        return 0

    if args.command == "profile":
        p = store.profile(args.provider)
        if args.json:
            sys.stdout.write(json.dumps(p.to_dict(), indent=2) + "\n")
        else:
            sys.stdout.write(f"Provider: {p.provider}\n")
            sys.stdout.write(f"  Events: {p.total_events}\n")
            sys.stdout.write(f"  Success: {p.success_rate:.0%}\n")
            sys.stdout.write(f"  Friction: {p.friction_rate:.0%}\n")
            sys.stdout.write(f"  Optimal level: {p.optimal_level}\n")
            sys.stdout.write(f"  Drift: {'DETECTED' if p.drift_detected else 'none'}\n")
            if p.top_triggers:
                sys.stdout.write(f"  Triggers: {', '.join(t[0] for t in p.top_triggers[:5])}\n")
        return 0

    if args.command == "record":
        event = store.record_interaction(
            provider=args.provider,
            model=args.model,
            outcome=args.outcome,
            quality_score=args.quality,
            modulation_level=args.level,
            trigger_terms=args.triggers,
        )
        sys.stdout.write(f"Recorded: {event.provider} {event.outcome} (quality={event.quality_score})\n")
        return 0

    if args.command == "events":
        events = store.load_events(limit=20)
        if args.json:
            sys.stdout.write(json.dumps([e.to_dict() for e in events], indent=2) + "\n")
        else:
            for e in events[-10:]:
                sys.stdout.write(
                    f"  {e.provider:>10} | {e.outcome:>13} | "
                    f"q={e.quality_score:.2f} | lvl={e.modulation_level}\n"
                )
        return 0

    if args.command == "clear":
        store.clear()
        sys.stdout.write("Store cleared.\n")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

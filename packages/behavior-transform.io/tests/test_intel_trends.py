import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from provider_intelligence import IntelStore
from intel_trends import analyze_trends, TrendReport


def _seed(store, provider, events_spec):
    """Seed store with events. events_spec: list of (outcome, level, quality)."""
    base_ts = time.time() - 3600
    for i, (outcome, level, quality) in enumerate(events_spec):
        store.record_interaction(
            provider=provider,
            modulation_level=level,
            outcome=outcome,
            quality_score=quality,
        )


def test_empty_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        report = analyze_trends(store=store)
        assert report.total_events == 0
        assert report.trends == []


def test_basic_trend_report():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        _seed(store, "anthropic", [
            ("success", 0, 0.9),
            ("success", 0, 0.85),
            ("hard_refusal", 0, 0.1),
            ("success", 1, 0.8),
            ("success", 2, 0.95),
            ("hedged", 1, 0.4),
            ("success", 0, 0.9),
            ("success", 2, 0.9),
            ("success", 1, 0.85),
            ("success", 0, 0.92),
        ])
        report = analyze_trends(store=store)
        assert report.total_events == 10
        assert len(report.windows) == 2
        assert len(report.level_effectiveness) >= 1
        assert report.windows[0].event_count < report.windows[1].event_count


def test_provider_filter():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        _seed(store, "anthropic", [("success", 0, 0.9)] * 5)
        _seed(store, "openai", [("hard_refusal", 0, 0.1)] * 3)
        report = analyze_trends(provider="anthropic", store=store)
        assert report.total_events == 5
        assert report.provider == "anthropic"


def test_level_effectiveness():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        _seed(store, "anthropic", [
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            ("success", 2, 0.9),
            ("success", 2, 0.85),
            ("success", 2, 0.9),
        ])
        report = analyze_trends(store=store)
        level_map = {le.level: le for le in report.level_effectiveness}
        assert level_map[0].success_rate == 0.0
        assert level_map[2].success_rate == 1.0


def test_trend_direction():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        # Historical: mostly failures
        _seed(store, "anthropic", [
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            ("hard_refusal", 0, 0.1),
            # Recent: mostly successes
            ("success", 2, 0.9),
            ("success", 2, 0.9),
            ("success", 2, 0.95),
        ])
        report = analyze_trends(store=store)
        success_trend = next(
            t for t in report.trends if t.metric == "success_rate"
        )
        assert success_trend.direction == "improving"
        friction_trend = next(
            t for t in report.trends if t.metric == "friction_rate"
        )
        assert friction_trend.direction == "improving"


def test_report_summary_text():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        _seed(store, "anthropic", [("success", 0, 0.9)] * 5)
        report = analyze_trends(store=store)
        text = report.summary()
        assert "Trend Report" in text
        assert "5" in text

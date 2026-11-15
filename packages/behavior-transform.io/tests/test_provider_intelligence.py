import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import time
import pytest

from provider_intelligence import (
    IntelEvent,
    ProviderProfile,
    IntelSummary,
    IntelStore,
)


@pytest.fixture
def store(tmp_path):
    return IntelStore(store_dir=tmp_path / "intel")


# --- IntelEvent ---

def test_event_to_dict():
    event = IntelEvent(
        timestamp=1000.0,
        provider="anthropic",
        model="claude-3",
        outcome="success",
        quality_score=0.95,
    )
    d = event.to_dict()
    assert d["provider"] == "anthropic"
    assert d["outcome"] == "success"
    assert d["quality_score"] == 0.95


def test_event_from_dict():
    d = {
        "timestamp": 1000.0,
        "provider": "openai",
        "model": "gpt-4",
        "outcome": "hedged",
        "quality_score": 0.6,
        "hedge_count": 3,
        "trigger_terms": ["exploit"],
    }
    event = IntelEvent.from_dict(d)
    assert event.provider == "openai"
    assert event.outcome == "hedged"
    assert event.trigger_terms == ["exploit"]


def test_event_to_json():
    event = IntelEvent(timestamp=1.0, provider="local")
    j = event.to_json()
    parsed = json.loads(j)
    assert parsed["provider"] == "local"


# --- IntelStore ---

def test_store_record_and_load(store):
    event = IntelEvent(
        timestamp=time.time(),
        provider="anthropic",
        outcome="success",
        quality_score=0.9,
    )
    store.record(event)
    events = store.load_events()
    assert len(events) == 1
    assert events[0].provider == "anthropic"


def test_store_record_interaction(store):
    event = store.record_interaction(
        provider="openai",
        model="gpt-4",
        outcome="soft_refusal",
        quality_score=0.3,
        modulation_level=2,
        trigger_terms=["exploit", "payload"],
    )
    assert event.provider == "openai"
    events = store.load_events()
    assert len(events) == 1


def test_store_multiple_events(store):
    for i in range(5):
        store.record_interaction(
            provider="anthropic",
            outcome="success" if i % 2 == 0 else "hedged",
            quality_score=0.8 if i % 2 == 0 else 0.4,
            modulation_level=i + 1,
        )
    events = store.load_events()
    assert len(events) == 5


def test_store_load_with_limit(store):
    for i in range(10):
        store.record_interaction(provider="local", outcome="success")
    events = store.load_events(limit=3)
    assert len(events) == 3


def test_store_clear(store):
    store.record_interaction(provider="test", outcome="success")
    store.clear()
    events = store.load_events()
    assert len(events) == 0


def test_store_load_empty(store):
    events = store.load_events()
    assert events == []


# --- ProviderProfile ---

def test_profile_empty_provider(store):
    profile = store.profile("nonexistent")
    assert profile.total_events == 0
    assert profile.success_rate == 0.0


def test_profile_single_provider(store):
    for i in range(10):
        store.record_interaction(
            provider="anthropic",
            outcome="success" if i < 7 else "soft_refusal",
            quality_score=0.9 if i < 7 else 0.3,
            modulation_level=2,
            trigger_terms=["exploit"] if i >= 7 else [],
        )
    profile = store.profile("anthropic")
    assert profile.total_events == 10
    assert profile.success_rate == 0.7
    assert profile.friction_rate == 0.3
    assert profile.optimal_level == 2


def test_profile_trigger_tracking(store):
    store.record_interaction(
        provider="openai", outcome="hedged",
        trigger_terms=["exploit", "payload"],
    )
    store.record_interaction(
        provider="openai", outcome="hedged",
        trigger_terms=["exploit", "inject"],
    )
    profile = store.profile("openai")
    triggers = dict(profile.top_triggers)
    assert triggers.get("exploit", 0) == 2


def test_profile_to_dict(store):
    store.record_interaction(provider="test", outcome="success", quality_score=0.9)
    profile = store.profile("test")
    d = profile.to_dict()
    assert "provider" in d
    assert "success_rate" in d
    assert "friction_rate" in d
    assert "optimal_level" in d


# --- IntelSummary ---

def test_summary_empty(store):
    s = store.summary()
    assert s.total_events == 0
    assert s.providers == []


def test_summary_multi_provider(store):
    for p in ["anthropic", "openai", "gemini"]:
        for i in range(5):
            store.record_interaction(
                provider=p,
                outcome="success" if i < 3 else "hedged",
                quality_score=0.8,
                modulation_level=2,
            )
    s = store.summary()
    assert s.total_events == 15
    assert len(s.providers) == 3
    assert s.global_success_rate == 9 / 15


def test_summary_to_dict(store):
    store.record_interaction(provider="local", outcome="success")
    s = store.summary()
    d = s.to_dict()
    assert "total_events" in d
    assert "providers" in d
    assert "global_friction_rate" in d
    assert "most_effective_level" in d


# --- Drift detection ---

def test_drift_detection(store):
    # First 80%: low friction
    for i in range(16):
        store.record_interaction(provider="anthropic", outcome="success")
    # Last 20%: high friction
    for i in range(4):
        store.record_interaction(provider="anthropic", outcome="hard_refusal")
    profile = store.profile("anthropic")
    assert profile.drift_detected is True


def test_no_drift_stable(store):
    for i in range(20):
        store.record_interaction(provider="stable", outcome="success")
    profile = store.profile("stable")
    assert profile.drift_detected is False

"""Time to the first streamed text, with the provider's own wait taken out.

Budget: 50 ms of Flywheel's own time per turn, as the median of five turns
after one warm-up turn, for each hosted dialect, against a loopback stub that
holds its first byte for 150 ms (tests/hosted_stream_stub.py).

Where the figure comes from: 30 turns per dialect at stub delays of 50 ms and
300 ms, on Windows 11 with Python 3.12.10, measured 2026-11-13 while other
work was running on the machine. Medians were 1.6 to 1.9 ms, 95th percentiles
9 to 25 ms, and the slowest single turn 38 ms. The budget sits above the
slowest turn seen and far below a delay a person would notice.

What the figure leaves out: the credential lookup in the OS key store (the
stub backends carry a test key directly), DNS and TLS to a real provider, and
the first turn's module imports.

Control: the same measurement with 200 ms added on Flywheel's side of the
wire must break the budget. A timing check that could not fail would say
nothing.
"""
import statistics

import pytest

from tests.hosted_stream_fixtures import PROVIDERS
from tests.hosted_stream_stub import overheads

BUDGET_SECONDS = 0.050
STUB_DELAY = 0.150
TURNS = 5


def within_budget(samples: list) -> bool:
    return statistics.median(samples) < BUDGET_SECONDS


@pytest.mark.parametrize("provider", PROVIDERS)
def test_first_streamed_text_arrives_within_the_budget(tmp_path, provider):
    samples = overheads(provider, str(tmp_path), delay=STUB_DELAY, turns=TURNS)
    assert len(samples) == TURNS
    assert within_budget(samples), [round(s * 1000, 1) for s in samples]
    # Each turn waited for the stub: a turn that skipped the network would have
    # finished before the stub's delay and shown up as a large negative sample.
    assert min(samples) > -0.010


def test_the_stub_delay_is_subtracted_not_hidden(tmp_path):
    """A longer provider wait leaves Flywheel's share inside the same budget."""
    samples = overheads("anthropic", str(tmp_path), delay=0.4, turns=3)
    assert within_budget(samples), [round(s * 1000, 1) for s in samples]


def test_the_budget_fails_when_flywheel_adds_200_ms(tmp_path):
    samples = overheads("openai", str(tmp_path), delay=STUB_DELAY, turns=TURNS,
                        client_delay=0.200)
    assert not within_budget(samples), [round(s * 1000, 1) for s in samples]
    assert statistics.median(samples) >= 0.200

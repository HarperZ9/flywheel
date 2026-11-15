"""Name the input of a failing test.

Long canaries are random text. Each test draws them from one seed, taken from
CANON_CANARY_SEED when it is set. When a test that made a canary fails, the
report carries the seed and the command that replays it.
"""
from __future__ import annotations

import pytest

from ._context_fixtures import SEED_ENV, canary_seed, start_canary_run


@pytest.fixture(autouse=True)
def _canary_seed():
    start_canary_run()
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    seed, calls = canary_seed()
    if calls:
        report.sections.append((
            "canary seed",
            f"{SEED_ENV}={seed} ({calls} long canaries made)\n"
            f'replay: {SEED_ENV}={seed} python -m pytest "{item.nodeid}"',
        ))

"""Windows-only cleanup support for CrewAI's existing pytest modules."""

from collections.abc import Generator
import gc

from lib.crewai.tests.utils import wait_for_event_handlers
import pytest


@pytest.fixture(autouse=True)
def drain_crewai_handlers_before_storage_cleanup(
    setup_test_environment: None,
) -> Generator[None, None, None]:
    """Release async handlers and cyclic SQLite objects before temp cleanup."""
    yield
    wait_for_event_handlers()
    gc.collect()

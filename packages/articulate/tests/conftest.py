import os
import sys

# src-layout: make the package importable without an editable install.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest


@pytest.fixture(autouse=True)
def _isolated_house_settings(tmp_path_factory):
    """No test reads or writes the real user's house-voice settings; each starts
    from the shipped defaults. A private MonkeyPatch, not the shared fixture, so
    a test's own monkeypatch (a chdir, for example) is undone before that test's
    other fixtures tear down, as it was before this fixture existed."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path_factory.mktemp("house-config")))
    for name in ("ARTICULATE_HOUSE_VOICE", "ARTICULATE_HOUSE_LENGTH", "ARTICULATE_HOUSE_HEADINGS",
                 "ARTICULATE_HOUSE_LISTS", "ARTICULATE_HOUSE_FIRST_PERSON",
                 "ARTICULATE_HOUSE_LIMITS", "ARTICULATE_HOUSE_END_LINE"):
        monkeypatch.delenv(name, raising=False)
    yield
    monkeypatch.undo()

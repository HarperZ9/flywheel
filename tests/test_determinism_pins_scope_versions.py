"""The committed v1 determinism pin file still reads after the scope migration."""
from harness.scope import scope_list
from tests.test_determinism_pins import D


def test_the_committed_v1_pin_file_still_reads():
    doc = D.load(D.DEFAULT_PINS_PATH)
    assert doc["schema"] == D.SCHEMA_V1
    assert scope_list(doc) and "scope" not in doc

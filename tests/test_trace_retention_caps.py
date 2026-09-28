"""I6: every cap a store declares names the test that covers its behavior
at the cap, and that test exists, or names the package that defers it."""
from pathlib import Path
import re

from harness import trace_inventory as inv

ROOT = Path(__file__).resolve().parents[1]


def _covered(test: str) -> bool:
    if test.startswith("deferred: "):
        return bool(re.search(r"\((7\.\d+|[A-Z]{1,3}-?\d+[a-z]?\d?)\)", test))
    path, _, name = test.partition("::")
    source = ROOT / path
    if not name or not source.is_file():
        return False
    text = source.read_text(encoding="utf-8")
    if path.endswith(".py"):
        return re.search(rf"^def {re.escape(name)}\(", text, re.MULTILINE) is not None
    return f"'{name}'" in text or f'"{name}"' in text


def test_every_declared_cap_names_a_test_that_exists():
    caps = [(store.id, cap) for store in inv.stores() for cap in store.caps]
    assert caps, "the inventory declares caps"
    missing = [(sid, cap.test) for sid, cap in caps if not _covered(cap.test)]
    assert missing == []


def test_a_cap_naming_a_missing_test_is_caught():
    assert not _covered("tests/test_gateway_agent_trace.py::test_no_such_test")
    assert not _covered("tests/no_such_file.py::test_x")
    assert not _covered("deferred: sometime")

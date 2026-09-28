"""The frozen gateway carries every trace custody module (scripts/frozen_trace_imports.py).

The custody inventory resolves adapters from dotted strings, which PyInstaller
cannot follow, so a module reached only that way would be missing from the
Windows app and its `/api/traces/*` export or delete would fail there while a
pip install works. These checks tie the literal list to the source tree and to
the inventory, and check that the spec adds the list to its hidden imports.
"""
from __future__ import annotations

from pathlib import Path

from harness import trace_inventory as inv
from scripts.frozen_trace_imports import TRACE_CUSTODY_HIDDEN_IMPORTS

REPO = Path(__file__).resolve().parents[1]
HOOK_ENTRY = "harness.capture_hooks.__main__"


def _module_path(name: str) -> Path:
    parts = name.split(".")
    package = REPO.joinpath(*parts) / "__init__.py"
    return package if package.exists() else REPO.joinpath(*parts[:-1]) / f"{parts[-1]}.py"


def _trace_modules() -> set[str]:
    harness = REPO / "harness"
    names = {f"harness.{p.stem}" for p in harness.glob("trace_*.py")}
    hooks = harness / "capture_hooks"
    names |= {f"harness.capture_hooks.{p.stem}" for p in hooks.glob("*.py")
              if p.stem != "__init__"}
    return (names | {"harness.capture_hooks"}) - {HOOK_ENTRY}


def _adapter_modules() -> set[str]:
    names = set()
    for store in inv.stores():
        for op in inv.OPERATIONS:
            value = getattr(store, op)
            if isinstance(value, str):
                names.add(value.rpartition(".")[0])
    return names


def missing(listed, required) -> list[str]:
    return sorted(set(required) - set(listed))


def test_every_listed_module_exists():
    absent = [name for name in TRACE_CUSTODY_HIDDEN_IMPORTS if not _module_path(name).is_file()]
    assert absent == []
    assert len(set(TRACE_CUSTODY_HIDDEN_IMPORTS)) == len(TRACE_CUSTODY_HIDDEN_IMPORTS)


def test_every_trace_and_capture_hook_module_is_listed():
    assert missing(TRACE_CUSTODY_HIDDEN_IMPORTS, _trace_modules()) == []


def test_every_inventory_adapter_module_is_listed():
    adapters = _adapter_modules()
    assert "harness.store_tombstone" in adapters and "harness.trace_delete_apply" in adapters
    assert missing(TRACE_CUSTODY_HIDDEN_IMPORTS, adapters) == []


def test_the_hook_entry_stays_out_of_the_engine():
    assert HOOK_ENTRY not in TRACE_CUSTODY_HIDDEN_IMPORTS


def test_the_spec_adds_the_list_to_its_hidden_imports():
    spec = (REPO / "packaging" / "flywheel-gateway.spec").read_text(encoding="utf-8")
    assert "from scripts.frozen_trace_imports import TRACE_CUSTODY_HIDDEN_IMPORTS" in spec
    hidden = spec.split("hiddenimports=[", 1)[1].split("],", 1)[0]
    assert "*TRACE_CUSTODY_HIDDEN_IMPORTS," in hidden


def test_control_a_dropped_module_is_reported():
    """False-success control: removing one adapter module from the list must
    show up in the check the tests above rely on."""
    shortened = [n for n in TRACE_CUSTODY_HIDDEN_IMPORTS if n != "harness.trace_meta_adapters"]
    assert missing(shortened, _adapter_modules()) == ["harness.trace_meta_adapters"]
    assert missing(shortened, _trace_modules()) == ["harness.trace_meta_adapters"]

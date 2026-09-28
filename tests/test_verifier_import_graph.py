import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _load_verifier_stdlib():
    spec = importlib.util.spec_from_file_location(
        "verifier_stdlib", ROOT / "scripts" / "check_verifier_stdlib.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _third_party_names(hits: list[str]) -> set[str]:
    return {hit.rsplit(" ", 1)[-1] for hit in hits}


def test_package_initializer_forbidden_import_is_in_verifier_closure(
        tmp_path, monkeypatch):
    # Break caught: resolving only module.py makes package/__init__.py invisible.
    harness = tmp_path / "harness"
    _write(harness / "package_gate" / "__init__.py", "import requests\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)

    reached, hits = vs.closure(["package_gate"])

    assert "package_gate" in reached
    assert "requests" in _third_party_names(hits)


def test_package_relative_sibling_import_reaches_forbidden_child(
        tmp_path, monkeypatch):
    # Break caught: `from . import child` must enqueue package.child.
    harness = tmp_path / "harness"
    _write(harness / "relpkg" / "__init__.py", "from . import child\n")
    _write(harness / "relpkg" / "child.py", "import numpy\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)

    reached, hits = vs.closure(["relpkg"])

    assert "relpkg.child" in reached
    assert "numpy" in _third_party_names(hits)


def test_root_harness_initializer_forbidden_import_is_in_verifier_closure(
        tmp_path, monkeypatch):
    # Break caught: harness/__init__.py is part of importing any harness module.
    harness = tmp_path / "harness"
    _write(harness / "__init__.py", "import requests\n")
    _write(harness / "entry.py", "import json\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)

    reached, hits = vs.closure(["entry"])

    assert "__init__" in reached
    assert "requests" in _third_party_names(hits)


@pytest.mark.parametrize(
    "import_line",
    [
        "import harness.abspkg.child\n",
        "from harness.abspkg import child\n",
        "from harness.abspkg.child import VALUE\n",
    ],
)
def test_absolute_harness_submodule_import_includes_parent_initializer(
        tmp_path, monkeypatch, import_line):
    # Break caught: `import harness.pkg.child` must not truncate to pkg only,
    # and importing a submodule must also traverse the package initializer.
    harness = tmp_path / "harness"
    _write(harness / "entry.py", import_line)
    _write(harness / "abspkg" / "__init__.py", "import requests\n")
    _write(harness / "abspkg" / "child.py", "import numpy\nVALUE = 7\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)

    reached, hits = vs.closure(["entry"])

    assert {"abspkg", "abspkg.child"}.issubset(reached)
    assert {"requests", "numpy"}.issubset(_third_party_names(hits))


def test_clean_stdlib_package_import_graph_passes(tmp_path, monkeypatch):
    # Break caught: stdlib-only packages should resolve fully without false hits.
    harness = tmp_path / "harness"
    _write(
        harness / "stdlib_pkg" / "__init__.py",
        "import json\nfrom . import child\n")
    _write(harness / "stdlib_pkg" / "child.py", "from pathlib import Path\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)

    reached, hits = vs.closure(["stdlib_pkg"])

    assert {"stdlib_pkg", "stdlib_pkg.child"}.issubset(reached)
    assert hits == []


def test_main_fails_when_relative_from_import_alias_is_missing(
        tmp_path, monkeypatch, capsys):
    # Break caught: `from . import missing_child` must not be dropped just
    # because no file exists yet.
    harness = tmp_path / "harness"
    _write(harness / "rel_missing" / "__init__.py",
           "from . import missing_child\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)
    monkeypatch.setattr(vs, "VERIFIER_ENTRY_POINTS", ["rel_missing"])

    exit_code = vs.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "rel_missing.missing_child" in output


def test_main_fails_when_harness_from_import_alias_is_missing(
        tmp_path, monkeypatch, capsys):
    # Break caught: `from harness import missing_local` must not be dropped just
    # because no file exists yet.
    harness = tmp_path / "harness"
    _write(harness / "__init__.py", "import json\n")
    _write(harness / "entry.py", "from harness import missing_local\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)
    monkeypatch.setattr(vs, "VERIFIER_ENTRY_POINTS", ["entry"])

    exit_code = vs.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "missing_local" in output


def test_main_allows_from_package_exported_values(tmp_path, monkeypatch,
                                                  capsys):
    # Negative control: exported names defined in a package initializer are not
    # necessarily child modules.
    harness = tmp_path / "harness"
    _write(harness / "__init__.py", "import json\n")
    _write(harness / "entry.py",
           "from harness.exported import VALUE, helper\n")
    _write(
        harness / "exported" / "__init__.py",
        "VALUE = 7\n\ndef helper():\n    return VALUE\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)
    monkeypatch.setattr(vs, "VERIFIER_ENTRY_POINTS", ["entry"])

    exit_code = vs.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "UNRESOLVED LOCAL IMPORT" not in output


def test_main_rejects_import_of_conditionally_bound_package_value(
        tmp_path, monkeypatch, capsys):
    # Break caught: a name assigned only inside a conditional body is not a
    # guaranteed package export at import time.
    harness = tmp_path / "harness"
    _write(harness / "__init__.py", "import json\n")
    _write(harness / "entry.py", "from harness.pkg import missing_local\n")
    _write(harness / "pkg" / "__init__.py",
           "if False:\n    missing_local = 1\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)
    monkeypatch.setattr(vs, "VERIFIER_ENTRY_POINTS", ["entry"])

    exit_code = vs.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "pkg.missing_local" in output


def test_main_fails_when_local_import_cannot_be_resolved(
        tmp_path, monkeypatch, capsys):
    # Break caught: a missing local module must not disappear from the gate.
    harness = tmp_path / "harness"
    _write(harness / "entry.py", "import harness.missing_local\n")
    vs = _load_verifier_stdlib()
    monkeypatch.setattr(vs, "HARNESS", harness)
    monkeypatch.setattr(vs, "VERIFIER_ENTRY_POINTS", ["entry"])

    exit_code = vs.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "missing_local" in output

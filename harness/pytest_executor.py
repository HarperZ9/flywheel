"""Untrusted pytest executor: report observations, never decide acceptance.

This process imports candidate and test code. Its JUnit, return code, and module
report are therefore evidence claims from an adversarial process. The trusted
parent validates their closed shape after exit and never turns a positive claim
from this process into PASS without an independent checker.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys

SCHEMA = "flywheel.python-module-provenance/v2"


def _module_name(ref: str) -> tuple[str, bool]:
    path = PurePosixPath(ref)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
        raise ValueError("candidate provenance requires a relative Python source")
    if path.name == "__init__.py":
        if len(path.parts) < 2:
            raise ValueError("top-level __init__.py has no stable module identity")
        return ".".join(path.parts[:-1]), True
    return ".".join((*path.parts[:-1], path.stem)), False


class ExactSourceLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, module: str, path: Path, source: bytes, package: bool):
        self.module, self.path, self.source, self.package = module, path, source, package
        self.loads = 0; self.loaded_module = None

    def find_spec(self, fullname, path=None, target=None):
        del path, target
        if fullname == self.module:
            return importlib.util.spec_from_loader(fullname, self,
                                                    is_package=self.package)
        return None

    def create_module(self, spec):
        del spec
        return None

    def exec_module(self, module):
        code = compile(self.source.decode("utf-8", "strict"), str(self.path),
                       "exec", dont_inherit=True)
        module.__file__ = str(self.path)
        if self.package:
            module.__path__ = [str(self.path.parent)]
            module.__package__ = self.module
        else:
            module.__package__ = self.module.rpartition(".")[0]
        self.loads += 1; self.loaded_module = module
        exec(code, module.__dict__)


def _parse(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--candidate-ref", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--junit", required=True)
    parser.add_argument("--provenance", required=True)
    values, pytest_args = parser.parse_known_args(argv)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    return values, pytest_args


def _write_report(values, loader, actual) -> None:
    current = sys.modules.get(loader.module)
    report = {"schema": SCHEMA, "module": loader.module,
        "source_ref": values.candidate_ref, "source_sha256": actual,
        "loaded": loader.loads > 0, "load_count": loader.loads,
        "origin": values.candidate_ref if current is loader.loaded_module else None,
        "binding": "exact-source-compile/v1",
        "authority": "untrusted-test-process/v1"}
    Path(values.provenance).write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def main(argv=None) -> int:
    values, pytest_args = _parse(argv)
    work = Path(values.workdir).resolve(strict=True)
    source_path = (work / PurePosixPath(values.candidate_ref)).resolve(strict=True)
    if work not in source_path.parents:
        raise ValueError("candidate source escapes protected workdir")
    source = source_path.read_bytes()
    actual = "sha256:" + hashlib.sha256(source).hexdigest()
    if actual != values.candidate_sha256:
        raise ValueError("candidate source digest changed before bootstrap")
    # Loading pytest before candidate code reduces accidental shadowing, but it
    # is not a trust boundary: candidate code shares this interpreter and may
    # mutate any cached function. The trusted parent treats all positive output
    # from this process as non-dispositive.
    import pytest
    pytest_main = pytest.main
    module_name, package = _module_name(values.candidate_ref)
    loader = ExactSourceLoader(module_name, source_path, source, package)
    sys.meta_path.insert(0, loader); sys.path.insert(0, str(work))
    rc = 3
    try:
        spec = loader.find_spec(module_name)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module; spec.loader.exec_module(module)
        # Persist this process's load observation before pytest begins so a
        # later timeout still carries it; the parent labels it untrusted.
        _write_report(values, loader, actual)
        rc = int(pytest_main([*pytest_args, "-p", "no:cacheprovider",
                              f"--junitxml={values.junit}", "-q"]))
    finally:
        _write_report(values, loader, actual)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

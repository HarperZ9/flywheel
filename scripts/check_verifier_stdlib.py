"""check_verifier_stdlib.py -- the offline verifier must run on a bare interpreter.

The promise a stranger relies on is: clone the repo, run the verifier, no pip
install, no network, no GPU. That promise is a property of the VERIFIER PATH,
not of harness/ as a whole. Some modules legitimately need heavy dependencies
(serve.py runs a model, quant_dither.py quantizes) and they are not on that
path.

So this does not scan harness/ blindly. It walks the transitive import closure
of the verifier entry points and asserts that nothing reachable from them
imports a third-party package. That is the actual property, and it fails the
moment somebody adds `import torch` to a module the gate happens to reach.

This is static import analysis against the known THIRD_PARTY set, not a proof
that arbitrary initializer code executes successfully. Dynamic import strings
and runtime attribute mutation require separate execution checks.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness"

# The chain a stranger must be able to run offline.
VERIFIER_ENTRY_POINTS = [
    "gate",             # the disproof gate
    "verdict",          # the verdict vocabulary
    "oracle",           # the verifier adapter
    "envelope",         # receipts
    "chain",            # tamper-evidence
    "witness",          # re-witnessing
    "matmul_oracle",    # the exact symbolic checker
    "advantages",       # the estimator, recorded in receipts
    "gateway_auth",     # the auth check
    "ed25519_verify",   # the signature verifier a stranger runs
    "receipt",          # the record a stranger re-derives
    "audit_receipt",    # the Layer-2 audit receipt a stranger re-derives + chain-checks
    "usage_receipt",    # the usage-metering receipt a stranger re-derives + re-checks
    "receipt_sign",     # the signature check a stranger runs
    "ots_verify",       # the OpenTimestamps -> Bitcoin proof a stranger rechecks
    "anchor",           # ties a signed head to its timestamp over one digest
    "why",              # answering doubt from the record alone
    "ledger",           # the receipt log and its inclusion proofs
    "merkle",           # the tree a stranger recomputes
    "bundle",           # what a stranger is handed and checks
    "contest",          # how a stranger disagrees on the record
    "byte_witness_verify",  # the byte witness a stranger rechecks against the bytes
    "action_witness",   # a run's action log, rechecked offline by whoever holds it
    "inspect_evidence_cli",  # external evidence intake without producer dependencies
    "inspect_fixture_contract",  # pinned importer contract checked offline
    "incident_sim_cli",  # submitted incident trace and bounded process audit
    # The certificate checkers ARE the accept path for the construction
    # families, and none of them were listed. Relative imports inside the
    # package resolved to bare names with no file at harness/ level, so the
    # whole subpackage was invisible to this gate.
    "certificates.base",
    "certificates.zarankiewicz",
    "certificates.independent",
    "certificates.generators",
    "certificates.crossing",
    "certificates.crossing_independent",
    "certificates.crossing_generator",
]

THIRD_PARTY = {
    "torch", "transformers", "peft", "trl", "numpy", "scipy", "pandas",
    "requests", "httpx", "pydantic", "vllm", "unsloth", "datasets",
    "accelerate", "bitsandbytes", "sentencepiece", "aiohttp", "flask",
    "fastapi", "yaml", "dotenv", "tqdm", "sklearn", "matplotlib",
}


def _module_path(name: str) -> Path | None:
    """Resolve a dotted local name to a file under harness/."""
    if not name or any(not part.isidentifier() for part in name.split(".")):
        return None
    base = HARNESS.joinpath(*name.split("."))
    package = base / "__init__.py"
    module = base.with_suffix(".py")
    return package if package.is_file() else module if module.is_file() else None


def _package_bindings(path: Path, excluded_line: int | None) -> set[str]:
    """Recognize unconditional declarations, without executing an initializer."""
    names: set[str] = set()
    pending = list(ast.parse(path.read_text(encoding="utf-8")).body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node.lineno != excluded_line:
                names.update(alias.asname or alias.name.split(".")[0]
                             for alias in node.names if alias.name != "*")
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(part.id for target in targets for part in ast.walk(target)
                         if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store))
    return names


def _imports_of(path: Path) -> tuple[set[str], set[str]]:
    """(local harness modules imported, third-party modules imported).

    Relative imports are resolved against the importing file's own package, so a
    `from .base import ...` inside harness/certificates/ reaches
    certificates.base and not a non-existent harness/base.py.
    """
    local: set[str] = set()
    third: set[str] = set()
    package_parts = list(path.parent.relative_to(HARNESS).parts)

    def add_from(base: str, node: ast.ImportFrom) -> None:
        if base:
            local.add(base)
        elif (HARNESS / "__init__.py").is_file():
            local.add("__init__")
        source = _module_path(base or "__init__")
        package = source is not None and source.name == "__init__.py"
        bindings = (_package_bindings(source, node.lineno if source == path else None)
                    if package else set())
        for alias in node.names:
            if alias.name == "*":
                continue
            child = ".".join(filter(None, (base, alias.name)))
            # Unknown package aliases must remain visible as unresolved names.
            # Declared values/functions are attributes, not missing child modules.
            if (_module_path(child) is not None or
                    (package or not base) and alias.name not in bindings):
                local.add(child)

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:                 # from .x import y
                up = node.level - 1
                if up > len(package_parts):
                    local.add("<invalid-relative-import>")
                    continue
                scope = package_parts[:len(package_parts) - up] if up else package_parts
                base = ".".join([*scope, *([node.module] if node.module else [])])
                add_from(base, node)
                continue
            if not node.module:
                continue
            head = node.module.split(".")[0]
            if head == "harness":
                add_from(node.module.partition(".")[2], node)
            elif head in THIRD_PARTY:
                third.add(f"{path.name}:{node.lineno} {head}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                head = a.name.split(".")[0]
                if head == "harness":
                    local.add(a.name.partition(".")[2] or "__init__")
                elif head in THIRD_PARTY:
                    third.add(f"{path.name}:{node.lineno} {head}")
    return local, third


def closure(entry_points: list[str]) -> tuple[set[str], list[str]]:
    """Walk the transitive local-import closure, collecting third-party hits."""
    seen: set[str] = set()
    hits: list[str] = []
    stack = list(entry_points)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        # Python executes each parent package initializer before its submodule.
        parents = ["__init__"] + [".".join(name.split(".")[:i])
                                   for i in range(1, len(name.split(".")))]
        stack.extend(parent for parent in parents if parent not in seen
                     and _module_path(parent) is not None)
        p = _module_path(name)
        if p is None:
            continue
        local, third = _imports_of(p)
        hits.extend(sorted(third))
        stack.extend(sorted(local - seen))
    return seen, hits


def main() -> int:
    reached, hits = closure(VERIFIER_ENTRY_POINTS)
    print(f"verifier closure: {len(reached)} modules reachable from "
          f"{len(VERIFIER_ENTRY_POINTS)} entry points")
    missing = sorted(name for name in reached if _module_path(name) is None)
    if missing:
        print("UNRESOLVED LOCAL IMPORT ON THE VERIFIER PATH:")
        for name in missing:
            print("  " + name)
    if hits:
        print("THIRD-PARTY IMPORT ON THE VERIFIER PATH:")
        for h in hits:
            print("  " + h)
    if hits or missing:
        return 1
    print("verifier path is stdlib-only: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())

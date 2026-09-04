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
    p = HARNESS.joinpath(*name.split(".")).with_suffix(".py")
    return p if p.exists() else None


def _imports_of(path: Path) -> tuple[set[str], set[str]]:
    """(local harness modules imported, third-party modules imported).

    Relative imports are resolved against the importing file's own package, so a
    `from .base import ...` inside harness/certificates/ reaches
    certificates.base and not a non-existent harness/base.py.
    """
    local: set[str] = set()
    third: set[str] = set()
    pkg = path.parent.relative_to(HARNESS).as_posix().replace("/", ".")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:                 # from .x import y
                if node.module:
                    # level 1 is this package, level 2 is its parent, and so on.
                    base = pkg.split(".") if pkg else []
                    up = node.level - 1
                    scope = base[:len(base) - up] if up else base
                    local.add(".".join([*scope, node.module]) if scope
                              else node.module)
                continue
            if not node.module:
                continue
            head = node.module.split(".")[0]
            if head == "harness":
                parts = node.module.split(".")
                if len(parts) > 1:
                    local.add(parts[1])
            elif head in THIRD_PARTY:
                third.add(f"{path.name}:{node.lineno} {head}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                head = a.name.split(".")[0]
                if head == "harness":
                    parts = a.name.split(".")
                    if len(parts) > 1:
                        local.add(parts[1])
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
    if hits:
        print("THIRD-PARTY IMPORT ON THE VERIFIER PATH:")
        for h in hits:
            print("  " + h)
        return 1
    print("verifier path is stdlib-only: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""compute_endpoint.py -- turn the completed pools into the preregistered endpoints.

Section 7 of the frozen preregistration allows ONE confirmatory run with no
interim analysis and no peeking. The walker was therefore built unable to read a
verdict. This tool is the other half of that: it reads verdicts, so it is built
unable to run before the pass is over.

Two refusals carry that, and neither has an override flag, because an override
is how a rule becomes a suggestion:

  * **No run_end, no endpoint.** The mechanical journal must carry the walk's
    own completion record. A partial pool is exactly the state in which a
    tempting early look is possible, so this is the state the tool refuses.
  * **No missing pair, or no endpoint.** The primary endpoint is defined over
    the union of bodies produced by ALL rungs. Computing it over the rungs that
    happen to be present would answer a different question under the same name,
    so a missing pair is named and the run stops.

Tests satisfy both guards honestly, by pointing the tool at a fixture pool whose
journal really does carry run_end, rather than by switching the guards off.

Stdlib only. No GPU, no network: every number here is a function of the cache.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness.certificates.base import parse_certificate            # noqa: E402
from harness.certificates.crossing import CrossingOracle           # noqa: E402
from harness.certificates.zarankiewicz import ZarankiewiczOracle   # noqa: E402
from harness.endpoint import (                                     # noqa: E402
    SCHEMA, body_digest, excluded_tasks, primary_endpoint,
    secondary_per_rung, union_of_bodies)
from harness.receipt import subject_digest                         # noqa: E402

# Declared here rather than inferred, because guessing a receipt's evidence
# vocabulary from an oracle's class name would be a silent classification. Both
# families check a SUBMITTED construction exactly, by arithmetic over data.
FAMILY_EVIDENCE = {"zarankiewicz": ("CONSTRUCTIVE", "construction_certificate"),
                   "rectilinear_crossing": ("CONSTRUCTIVE",
                                            "construction_certificate")}
ORACLES = {"zarankiewicz": ZarankiewiczOracle,
           "rectilinear_crossing": CrossingOracle}
# The generator that produced the instances, named by its import path so a
# reader can go and look at it rather than trust a label.
GENERATORS = {
    "zarankiewicz": "harness.certificates.generators.zarankiewicz_instance",
    "rectilinear_crossing":
        "harness.certificates.crossing_generator.crossing_instance"}


class EndpointGate(RuntimeError):
    """A refusal to compute an endpoint the protocol does not yet allow."""


def _load(name: str):
    """Load a sibling script as a module. The fill driver holds the frozen
    instance set and the rung-independent task ids; the walker holds the fixed
    family and rung order. Restating either here would be a second copy of a
    frozen rule, and two copies eventually disagree."""
    spec = importlib.util.spec_from_file_location(
        name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pinned_criteria(ledger: Path) -> dict:
    """The criterion ids and digests as FROZEN, read from the freeze entry.

    Not recomputed from the criterion objects in the tree: the endpoint must
    name what was pinned, and a digest recomputed from present-day code would
    silently paper over exactly the drift the pin exists to catch.
    """
    if not ledger.is_file():
        raise EndpointGate(f"no ledger at {ledger}; the pinned criterion "
                           "digests are not recoverable without it")
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("kind") == "prereg-freeze" and row.get("criterion_sha256"):
            return dict(row["criterion_sha256"])
    raise EndpointGate("the ledger carries no prereg-freeze entry with pinned "
                       "criterion digests")


def require_run_end(journal: Path) -> None:
    """Refuse until the walk has recorded its own completion."""
    if not journal.is_file():
        raise EndpointGate(
            f"no confirmatory journal at {journal.name}: without the walk's own "
            "record there is nothing to establish that the pass finished")
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("event") == "run_end":
                return
        except json.JSONDecodeError:
            continue
    raise EndpointGate(
        "the confirmatory journal carries no run_end. Section 7 forbids interim "
        "analysis, so this tool refuses to compute an endpoint over a pass that "
        "is still running. There is no flag to skip this.")


def require_every_pair(pool_root: Path, families, rungs) -> None:
    """Refuse unless every (family, rung) pair has a completed pool index."""
    missing = [f"{fam} @ {rung}" for fam in families for rung in rungs
               if not (pool_root / fam / rung.replace(":", "_")
                       / "pool_index.json").is_file()]
    if missing:
        raise EndpointGate(
            "the primary endpoint is defined over the union of bodies from ALL "
            "rungs, and these pairs have no completed pool index: "
            + ", ".join(missing) + ". Computing over the pairs that happen to "
            "be present would answer a different question under the same name.")


def load_pool(pair_dir: Path) -> dict:
    """The pool index enriched with the candidate bodies it names."""
    doc = json.loads((pair_dir / "pool_index.json").read_text(encoding="utf-8"))
    bodies = {}
    for entry in doc.get("entries", []):
        for slot in entry.get("slots", []):
            sha = slot.get("candidate_sha256")
            if sha is None or sha in bodies:
                continue
            path = pair_dir / "candidates" / (sha.split(":", 1)[-1] + ".txt")
            if not path.is_file():
                raise EndpointGate(
                    f"{pair_dir.name}: the index names candidate {sha} but no "
                    "such file exists; an endpoint over bodies cannot be "
                    "computed from an index whose candidates are missing")
            bodies[sha] = path.read_text(encoding="utf-8")
    doc["bodies"] = bodies
    return doc


def make_submit(family: str, criterion_id: str, criterion_sha256: str,
                instances: dict, prompt_hashes: dict, checker_sha256: str):
    """The accept path, as the callable harness/endpoint.py consumes.

    The rung is accepted and deliberately unused for anything except the record.
    That is the endpoint's whole point: if a rung could change either digest,
    the accept path would not be a function of the certificate.
    """
    oracle = ORACLES[family]()
    evidence_kind, tier = FAMILY_EVIDENCE[family]
    checker_module = type(oracle).__module__

    def submit(body: str, task_id: str, rung: str) -> dict:
        instance = instances[task_id]
        result = oracle.verify(body, task=instance)
        well_formed, _, _ = parse_certificate(body)
        return {
            "verdict": result.verdict_.value,
            "attribution": result.attribution.value,
            "well_formed": bool(well_formed),
            "verdict_digest": result.output_hash,
            "subject_digest": subject_digest(
                criterion_id=criterion_id, criterion_version=1,
                criterion_sha256=criterion_sha256, family=family,
                family_instance_id=task_id,
                generator_id=GENERATORS[family],
                generator_seed=int(instance.get("seed", 0)),
                candidate_sha256=body_digest(body),
                prompt_hash=prompt_hashes.get(task_id, ""),
                checker_module=checker_module,
                checker_source_sha256=checker_sha256,
                executes_candidate_code=oracle.executes_candidate_code,
                evidence_kind=evidence_kind, tier=tier),
        }
    return submit


def _sha256_of_file(path: Path) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def compute(pool_root: Path, journal: Path, families, rungs,
            ledger: Path) -> dict:
    require_run_end(journal)
    require_every_pair(pool_root, families, rungs)
    pinned = pinned_criteria(ledger)
    fill = _load("run_demo_pool")
    report = {"schema": SCHEMA, "pool_root": pool_root.name,
              "families": {}, "rungs": list(rungs),
              "pinned_criterion_sha256": pinned}
    for family in families:
        criterion_id = fill.FAMILIES[family]["criterion_id"]
        if criterion_id not in pinned:
            raise EndpointGate(
                f"criterion {criterion_id!r} for family {family!r} is not among "
                f"the pinned digests {sorted(pinned)}; the endpoint must name "
                "what was frozen, not what happens to be in the tree")
        instances = {fill.task_id_for(family, inst): inst
                     for inst in fill.build_instances(family)}
        pools = {rung: load_pool(pool_root / family / rung.replace(":", "_"))
                 for rung in rungs}
        prompt_hashes = {}
        for doc in pools.values():
            for entry in doc.get("entries", []):
                prompt_hashes.setdefault(entry["task_id"],
                                         entry.get("prompt_sha256", ""))
        checker_sha = _sha256_of_file(
            REPO / (ORACLES[family].__module__.replace(".", "/") + ".py"))
        submit = make_submit(family, criterion_id, pinned[criterion_id],
                             instances, prompt_hashes, checker_sha)
        union = union_of_bodies(pools)
        report["families"][family] = {
            "criterion_id": criterion_id,
            "primary": primary_endpoint(union, rungs, submit),
            "secondary": secondary_per_rung(pools, submit),
            "excluded_tasks": excluded_tasks(pools),
            "checker_source_sha256": checker_sha,
        }
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool-root", default=str(REPO / "artifacts" / "pool"))
    ap.add_argument("--journal", default=None,
                    help="defaults to confirmatory-journal.jsonl under the pool root")
    ap.add_argument("--out", default=str(REPO / "artifacts" / "endpoint"))
    ap.add_argument("--ledger",
                    default=str(REPO / "artifacts" / "prereg" / "ledger.jsonl"))
    args = ap.parse_args(argv)

    pool_root = Path(args.pool_root)
    journal = (Path(args.journal) if args.journal
               else pool_root / "confirmatory-journal.jsonl")
    walk = _load("run_confirmatory")
    try:
        report = compute(pool_root, journal, walk.FAMILIES, walk.RUNGS,
                         Path(args.ledger))
    except EndpointGate as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "endpoint-report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    for family, block in report["families"].items():
        p = block["primary"]
        print(f"{family}: {p['n_bodies']} bodies, "
              f"{p['n_disagreements']} disagreement(s), met={p['met']}")
    print(f"report -> {out / 'endpoint-report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

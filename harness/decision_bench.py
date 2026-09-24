"""Decision bench: suite manifests, the seal, runs on the open splits and policy
fitting. The sealed side (the single-use confirm, the pre-registered criteria,
the report and the command line) is in ``decision_bench_sealed``.

Suite manifest ``flywheel.decision-suite/v1``: ``schema``, ``family``,
``act_on`` (labels whose selection is the act, ``["false"]`` for F1), optional
``min_useful_coverage`` and ``build`` (builder parameters), and ``items``. An
item has ``item_id``, ``unit_id`` (the independent unit, a commit for F1),
``split``, ``state``, ``question`` (one /v1/systemone question), ``target``
(one of its real labels), ``tokens`` (what acting saves), ``certification_unit``
(exactly one per unit), ``label_kind``, ``label_source_ref`` and optional
``stratum``. A family builder is ``harness.decision_suites.<family>`` with
``build(**params) -> manifest``.

Runtime files sit beside the manifest: ``seal.json``,
``runs/<split>/<arm>.json``, ``runs/<split>/battery.json`` and
``cards/<arm>.json``. The seal is never replaced by a different hash, every
command after it refuses a manifest that no longer matches, and ``run``
refuses the sealed split. None of this proves a label, a model or a threshold
right; it records which rows were read and scored under which seal.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import decision_bench_metrics as metrics
from .classifier_dataset import VALID_LABEL_KINDS
from .decision_backends import read_items, resolve
from .decision_backends.controls import CONTROL_ARMS, battery
from .decision_contract import ID_PATTERN
from .evidence_json import canonical_sha256, strict_load_json
from .systemone_contract import (
    FAMILY_PATTERN, SystemOneError, answer_labels, validate_request)

SUITE_SCHEMA = "flywheel.decision-suite/v1"
SEAL_SCHEMA = "flywheel.decision-seal/v1"
RUN_SCHEMA = "flywheel.decision-bench-run/v1"
SPLITS = metrics.SPLIT_ORDER
OPEN_SPLITS = ("development", "calibration")
ITEM_KEYS = {"item_id", "unit_id", "split", "state", "question", "target", "tokens",
             "certification_unit", "label_kind", "label_source_ref"}
SUITE_KEYS = {"schema", "family", "act_on", "items"}
SUITE_OPTIONAL = {"min_useful_coverage", "build"}
MAX_JSON_BYTES = 1 << 30
DOES_NOT_PROVE = ("Label truth, independence of units, a model's quality, or that "
                  "future items behave like these.")


class BenchRefused(ValueError):
    """A bench rule refused the command; ``code`` is fixed and non-echoing."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def need(ok: object, code: str) -> None:
    if not ok:
        raise BenchRefused(code)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(arm: str) -> str:
    """A file-name-safe arm name."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", arm)[:120]


def read_json(path) -> dict:
    return strict_load_json(Path(path).read_bytes(), max_bytes=MAX_JSON_BYTES)


def maybe_json(path: Path) -> dict | None:
    return read_json(path) if path.exists() else None


def write_json(path: Path, value: dict, *, exclusive: str | None = None) -> None:
    """Write compact sorted JSON. With ``exclusive`` set, refuse with that code
    when the file exists; otherwise replace atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    if exclusive:
        try:
            with open(path, "xb") as fh:
                fh.write(data)
        except FileExistsError:
            raise BenchRefused(exclusive) from None
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _item(item: object, units: dict) -> None:
    need(type(item) is dict and ITEM_KEYS <= set(item) <= ITEM_KEYS | {"stratum"},
         "item_shape")
    for key in ("item_id", "unit_id"):
        need(type(item[key]) is str and ID_PATTERN.fullmatch(item[key]), key)
    need(item["split"] in SPLITS and type(item["state"]) is str, "item_split_state")
    try:
        validate_request({"model": "bench", "state": item["state"],
                          "questions": {item["item_id"]: item["question"]}})
    except SystemOneError:
        raise BenchRefused("item_question") from None
    need(item["target"] in answer_labels(item["question"]), "item_target")
    need(type(item["tokens"]) is int and item["tokens"] >= 0, "item_tokens")
    need(type(item["certification_unit"]) is bool, "item_certification_unit")
    need(item["label_kind"] in VALID_LABEL_KINDS
         and type(item["label_source_ref"]) is str and item["label_source_ref"]
         and type(item.get("stratum", "")) is str, "item_provenance")
    unit = units.setdefault(item["unit_id"], [item["split"], item["state"], 0])
    need(unit[:2] == [item["split"], item["state"]], "unit_split_or_state_mismatch")
    unit[2] += item["certification_unit"]


def validate_manifest(manifest: object) -> dict:
    """Check a suite manifest; refuse with a fixed code on the first defect."""
    need(type(manifest) is dict and SUITE_KEYS <= set(manifest)
         <= SUITE_KEYS | SUITE_OPTIONAL, "manifest_shape")
    need(manifest["schema"] == SUITE_SCHEMA and type(manifest["family"]) is str
         and FAMILY_PATTERN.fullmatch(manifest["family"]), "manifest_family")
    act_on, items = manifest["act_on"], manifest["items"]
    need(type(act_on) is list and act_on and len(set(act_on)) == len(act_on)
         and all(type(a) is str for a in act_on), "manifest_act_on")
    cover = manifest.get("min_useful_coverage", .3)
    need(type(cover) in (int, float) and 0 <= cover <= 1, "manifest_coverage")
    need(type(items) is list and items, "manifest_items")
    units: dict = {}
    for item in items:
        _item(item, units)
    need(len({i["item_id"] for i in items}) == len(items), "item_id_duplicate")
    need(all(u[2] == 1 for u in units.values()), "one_certification_unit_per_unit")
    return manifest


def seal_sha256(manifest: dict) -> str:
    """The seal: sha256 of the whole manifest in canonical JSON."""
    return canonical_sha256(manifest)


def seal(manifest_path) -> dict:
    """Write seal.json once. Resealing an unchanged manifest returns the seal."""
    path = Path(manifest_path)
    manifest = validate_manifest(read_json(path))
    digest, target = seal_sha256(manifest), path.parent / "seal.json"
    prior = maybe_json(target)
    if prior is not None:
        need(prior.get("seal_sha256") == digest, "seal_exists_with_other_hash")
        return prior
    by_split = {s: [i for i in manifest["items"] if i["split"] == s] for s in SPLITS}
    record = {
        "schema": SEAL_SCHEMA, "seal_sha256": digest, "family": manifest["family"],
        "sealed_at": now(), "leak": metrics.leak_report(manifest["items"]),
        "split_sha256": {s: canonical_sha256(v) for s, v in by_split.items()},
        "counts": {s: {"items": len(v), "units": len({i["unit_id"] for i in v})}
                   for s, v in by_split.items()},
        "does_not_prove": DOES_NOT_PROVE}
    write_json(target, record, exclusive="seal_exists_with_other_hash")
    return record


def load_sealed(manifest_path) -> tuple[dict, dict, Path]:
    """The manifest, its seal record and the suite directory, or a refusal."""
    path = Path(manifest_path)
    manifest = validate_manifest(read_json(path))
    record = maybe_json(path.parent / "seal.json")
    need(record is not None, "suite_not_sealed")
    need(record.get("seal_sha256") == seal_sha256(manifest), "manifest_changed_after_seal")
    return manifest, record, path.parent


def run_arms(manifest, record, split, specs, *, deadline_ms=2000, seed=1709,
             coverage=None, gates=None, log=None) -> dict:
    """Read one split with every arm the specs resolve to; return run records.
    ``gates`` maps a spec to the view arguments its card sets."""
    items = [i for i in manifest["items"] if i["split"] == split]
    need(items, "empty_split")
    cover = manifest.get("min_useful_coverage", .3) if coverage is None else coverage
    out = {}
    for spec in specs:
        gate = (gates or {}).get(spec, {})
        for arm, backend in resolve(spec, items=items, act_on=manifest["act_on"],
                                    seed=seed, coverage=cover):
            rows, units = read_items(backend, items, deadline_ms=deadline_ms, log=log)
            out[arm] = {
                "schema": RUN_SCHEMA, "seal_sha256": record["seal_sha256"],
                "family": manifest["family"], "split": split, "arm": arm,
                "spec": spec, "backend_id": backend.backend_id,
                "capabilities": backend.capabilities(), "rows": rows,
                "units": units, "gate": gate, "does_not_prove": DOES_NOT_PROVE,
                "summary": metrics.summarize(rows, units, manifest["act_on"], **gate)}
    return out


def control_battery(runs: dict, manifest: dict, record: dict) -> dict | None:
    """The split's battery when every control ran, bound to the seal."""
    if not all(arm in runs for arm in CONTROL_ARMS):
        return None
    result = battery({arm: runs[arm]["rows"] for arm in CONTROL_ARMS},
                     manifest["act_on"], leak=record["leak"])
    return {**result, "seal_sha256": record["seal_sha256"]}


def run(manifest_path, split: str, specs, *, deadline_ms: int = 2000,
        seed: int = 1709, coverage=None, log=None) -> dict:
    """Run arms on the development or calibration split and write run records.
    A ``controls`` run also writes the split's battery."""
    need(split in OPEN_SPLITS, "sealed_split_is_confirm_only")
    manifest, record, root = load_sealed(manifest_path)
    runs = run_arms(manifest, record, split, specs, deadline_ms=deadline_ms,
                    seed=seed, coverage=coverage, log=log)
    for arm, rec in runs.items():
        write_json(root / "runs" / split / f"{slug(arm)}.json", rec)
    result = control_battery(runs, manifest, record)
    if result is not None:
        write_json(root / "runs" / split / "battery.json", result)
    return {"split": split, "battery": None if result is None else result["status"],
            "arms": {arm: rec["summary"]["strata"]["all"]["certification_units"]
                     for arm, rec in runs.items()}}


def policy_rows(rows: list, *, certification_only: bool) -> list:
    """Bench rows in the ``decision_policy.fit_card`` row shape. A failed read
    has no reading, so fitting refuses rather than silently dropping it."""
    rows = [r for r in rows if r["certification_unit"] or not certification_only]
    need(all(r["raw"] is not None for r in rows), "arm_runs_have_failed_reads")
    return [{"split": r["split"], "target": r["target"], "case_id": r["item_id"],
             "source_group": r["unit_id"], "input_sha256": r["input_sha256"],
             "label_kind": r["label_kind"],
             "reading": {"type": r["question_type"], "raw": r["raw"],
                         "order_agreement": r["order_agreement"],
                         "label_mass": r["label_mass"]}} for r in rows]


def fit_policy(manifest_path, arm: str, *, act_on=None, alpha=.05, delta=.05,
               grid=None) -> dict:
    """Fit a card through ``decision_policy.fit_card`` on every development row
    and the calibration certification units, and write ``cards/<arm>.json``."""
    manifest, record, root = load_sealed(manifest_path)
    dev, cal = (maybe_json(root / "runs" / s / f"{slug(arm)}.json") for s in OPEN_SPLITS)
    need(all(r is not None and r["seal_sha256"] == record["seal_sha256"] for r in (dev, cal)),
         "arm_runs_missing_for_this_seal")
    from . import decision_policy  # imported here: the bench runs without the policy layer
    weights = {u["weights_sha256"] for u in cal["units"]}
    meta = {"family": manifest["family"], "backend_id": cal["backend_id"], "model_id": arm,
            "question_type": cal["rows"][0]["question_type"],
            "weights_sha256": weights.pop() if len(weights) == 1 else None}
    card = decision_policy.fit_card(
        policy_rows(dev["rows"], certification_only=False),
        policy_rows(cal["rows"], certification_only=True), alpha=alpha, delta=delta,
        act_on=act_on or manifest["act_on"], grid=list(grid or metrics.DEFAULT_GRID),
        meta=meta, min_useful_coverage=manifest.get("min_useful_coverage", .3))
    if card.get("bench_receipt_sha256") is None:
        card["bench_receipt_sha256"] = canonical_sha256(
            {"seal_sha256": record["seal_sha256"], "arm": arm,
             "runs": [canonical_sha256(r["rows"]) for r in (dev, cal)]})
    write_json(root / "cards" / f"{slug(arm)}.json", card)
    return card


def build_suite(family: str, out_dir, **params) -> Path:
    """Build a family suite with its builder and write ``manifest.json``."""
    need(type(family) is str and FAMILY_PATTERN.fullmatch(family), "manifest_family")
    out = Path(out_dir)
    need(not (out / "seal.json").exists(), "suite_already_sealed")
    builder = importlib.import_module(f"{__package__}.decision_suites.{family}")
    manifest = validate_manifest(builder.build(**params))
    write_json(out / "manifest.json", manifest)
    return out / "manifest.json"


def main(argv=None) -> int:
    """The command line lives in ``decision_bench_sealed`` (line budget)."""
    from .decision_bench_sealed import cli
    return cli(argv)


if __name__ == "__main__":
    sys.exit(main())

"""The sealed side of the decision bench: the single-use confirm, the increment 1
criteria of the design record (section 6.2), the report, and the command line
behind ``python -m harness.decision_bench``.

``confirm`` refuses unless the leak detector is clear, the calibration battery
passed under this seal, a card exists for the arm, and every baseline already
ran on calibration. It then claims ``confirm.json`` by exclusive create before
any backend reads a sealed item, so a second confirm on the seal is refused
even after a crash. The same call reads the baselines (the controls and lexical
by default), so arms are compared without a second confirm. ``--diagnostic``
reruns are allowed only once the confirm is spent and are written to
``diagnostics/``, never to ``confirm.json``.

Deleting ``confirm.json`` or copying the suite defeats the single-use rule; the
seal hash committed to the pre-registration record is the check on that. A
criterion that passes adopts nothing by itself; the decision stays with the
operator.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import decision_bench as bench
from . import decision_bench_metrics as metrics
from .evidence_json import canonical_sha256

CONFIRM_SCHEMA = "flywheel.decision-confirm/v1"
REPORT_SCHEMA = "flywheel.decision-bench-report/v1"
CARD_ACTS = ("statistical_candidate_only", "confirmed")
UNREACHABLE = 2.0  # above any correct_prob: an arm whose card may not act never acts
DEFAULT_BASELINES = ("controls", "lexical")
MAX_P95_MS, MAX_FULL_PASS_S = 2000.0, 90 * 60
DOES_NOT_PROVE = ("Correctness of any single decision, authorization, or that items "
                  "after the seal are exchangeable with it.")
need = bench.need


def card_gate(card: dict | None) -> dict:
    """The view arguments a card sets; an empty dict when there is no card."""
    if card is None:
        return {}
    acts = card.get("status") in CARD_ACTS and card.get("threshold") is not None
    temperature = card.get("temperature", 1.0) if card.get("temperature_applied") else 1.0
    return {"threshold": card["threshold"] if acts else UNREACHABLE,
            "temperature": temperature, "mass_floor": card.get("label_mass_min")}


def _card(root, spec: str) -> dict | None:
    return bench.maybe_json(root / "cards" / f"{bench.slug(spec)}.json")


def _claim(root, record: dict, arm: str, baselines: list, diagnostic: bool):
    """Check every precondition, then claim the seal (or name the diagnostic
    file). Returns ``(card, output_path)``."""
    seal = record["seal_sha256"]
    need(not record["leak"]["tripped"], "leak_detector_tripped")
    cal = root / "runs" / "calibration"
    battery = bench.maybe_json(cal / "battery.json")
    need(battery is not None and battery.get("seal_sha256") == seal
         and battery.get("status") == "pass", "calibration_controls_not_passed")
    card = _card(root, arm)
    need(arm != "controls" and card is not None, "no_card_for_arm")
    for spec in baselines:
        prior = bench.maybe_json(cal / f"{bench.slug(spec)}.json")
        need(spec == "controls" or (prior is not None and prior.get("seal_sha256") == seal),
             "baseline_not_run_on_calibration")
    claim = root / "confirm.json"
    if diagnostic:
        need(claim.exists(), "diagnostic_before_confirm")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return card, root / "diagnostics" / f"{stamp}-{bench.slug(arm)}.json"
    bench.write_json(claim, {"schema": CONFIRM_SCHEMA, "status": "claimed",
                             "seal_sha256": seal, "arm": arm, "claimed_at": bench.now()},
                     exclusive="confirm_already_spent")
    return card, claim


def confirm(manifest_path, arm: str, *, baselines=None, diagnostic: bool = False,
            deadline_ms: int = 2000, seed: int = 1709, log=None) -> dict:
    """The single sealed confirm for ``arm`` and its baselines."""
    manifest, record, root = bench.load_sealed(manifest_path)
    baselines = [b for b in (baselines or DEFAULT_BASELINES) if b != arm]
    card, out = _claim(root, record, arm, baselines, diagnostic)
    specs = [arm] + baselines
    gates = {s: card_gate(card if s == arm else _card(root, s)) for s in specs}
    runs = bench.run_arms(manifest, record, "sealed", specs, deadline_ms=deadline_ms,
                          seed=seed, gates=gates, log=log)
    sealed_battery = bench.control_battery(runs, manifest, record)
    result = {
        "schema": CONFIRM_SCHEMA, "status": "completed", "diagnostic": diagnostic,
        "seal_sha256": record["seal_sha256"], "arm": arm, "card": card,
        "card_sha256": canonical_sha256(card), "completed_at": bench.now(),
        "arms": runs, "battery": sealed_battery, "does_not_prove": DOES_NOT_PROVE,
        "headline": {"arm": arm, "diagnostic": diagnostic,
                     "battery": sealed_battery and sealed_battery["status"],
                     "certification_units":
                         runs[arm]["summary"]["strata"]["all"]["certification_units"]}}
    bench.write_json(out, result)
    return result


def _unit_tokens(rec: dict, act_on) -> dict:
    return {unit: sum(r["tokens"] for r in rows
                      if metrics.view(r, act_on, **rec["gate"])["acts"])
            for unit, rows in metrics.by_unit(rec["rows"]).items()}


def versus_lexical(conf: dict, act_on, *, n_boot: int = 1000) -> dict:
    """Criterion 3: per-unit tokens excluded minus lexical's, each at its own
    card, with a unit-clustered bootstrap lower bound."""
    if conf["arm"] == "lexical":
        return {"pass": None, "status": "not_applicable"}
    lexical = conf["arms"].get("lexical")
    if lexical is None or not lexical["gate"]:
        return {"pass": False, "status": "not_evaluable_without_a_lexical_card"}
    mine, theirs = _unit_tokens(conf["arms"][conf["arm"]], act_on), _unit_tokens(lexical, act_on)
    boot = metrics.cluster_bootstrap({u: mine[u] - theirs.get(u, 0) for u in mine},
                                     lambda xs: sum(xs) / len(xs), n_boot=n_boot)
    return {"pass": boot["low"] is not None and boot["low"] > 0,
            "status": "evaluated", "mean_token_difference": boot}


def criteria(conf: dict, manifest: dict, open_wall_s: float | None) -> dict:
    """Section 6.2, criteria 1 to 5, on the confirmed arm."""
    rec = conf["arms"][conf["arm"]]
    block = rec["summary"]["strata"]["all"]
    cert, questions = block["certification_units"], block["questions"]
    max_error = (conf["card"] or {}).get("max_error", .05)
    floor = manifest.get("min_useful_coverage", .3)
    p95 = rec["summary"]["latency_ms"]["p95"]
    sealed_s = sum(u["wall_ms"] for u in rec["units"]) / 1000
    full = None if open_wall_s is None else open_wall_s + sealed_s
    return {
        "1_miss_rate_bound": {"pass": cert["acted"] > 0 and cert["upper_error_bound"] <= max_error,
                              "upper_error_bound": cert["upper_error_bound"],
                              "max_error": max_error, "acted": cert["acted"]},
        "2_negatives_excluded": {"pass": (questions["act_recall"] or 0) >= floor,
                                 "act_recall": questions["act_recall"], "floor": floor},
        "3_more_tokens_than_lexical": versus_lexical(conf, manifest["act_on"]),
        "4_p95_latency": {"pass": p95 is not None and p95 <= MAX_P95_MS, "p95_ms": p95},
        "5_full_pass": {"pass": full is not None and full <= MAX_FULL_PASS_S,
                        "seconds": full}}


def _brief(rec: dict, act_on, gpu_rate) -> dict:
    views = [metrics.view(r, act_on, **rec["gate"]) for r in rec["rows"]]
    return {"backend_id": rec["backend_id"], "spec": rec["spec"], "gate": rec["gate"],
            "summary": rec["summary"],
            "headline": metrics.per_correct_act(views, rec["units"], gpu_rate=gpu_rate)}


def _open_runs(root, record: dict, act_on, gpu_rate) -> tuple[dict, dict, list]:
    runs, batteries, stale = {}, {}, []
    for split in bench.OPEN_SPLITS:
        runs[split] = {}
        for path in sorted((root / "runs" / split).glob("*.json")):
            rec = bench.read_json(path)
            if rec.get("seal_sha256") != record["seal_sha256"]:
                stale.append(f"{split}/{path.name}")
            elif path.name == "battery.json":
                batteries[split] = rec
            else:
                runs[split][rec["arm"]] = _brief(rec, act_on, gpu_rate)
    return runs, batteries, stale


def report(manifest_path, *, gpu_rate=None) -> dict:
    """Write ``report.json`` (``flywheel.decision-bench-report/v1``)."""
    manifest, record, root = bench.load_sealed(manifest_path)
    act_on = manifest["act_on"]
    runs, batteries, stale = _open_runs(root, record, act_on, gpu_rate)
    conf = bench.maybe_json(root / "confirm.json")
    done = conf is not None and conf.get("status") == "completed"
    if done and conf.get("battery"):
        batteries["sealed"] = conf["battery"]
    arm = conf["arm"] if conf else None
    open_s = [runs[s].get(arm, {}).get("headline", {}).get("wall_seconds")
              for s in bench.OPEN_SPLITS]
    void = record["leak"]["tripped"] or any(b["status"] != "pass" for b in batteries.values())
    body = {
        "schema": REPORT_SCHEMA, "seal_sha256": record["seal_sha256"],
        "family": manifest["family"], "leak": record["leak"], "runs": runs,
        "batteries": batteries, "stale_run_files": stale, "void": void,
        "confirm": None if conf is None else {
            "status": conf["status"], "arm": arm, "card": conf.get("card"),
            "arms": {a: _brief(r, act_on, gpu_rate) for a, r in conf.get("arms", {}).items()}},
        "criteria": criteria(conf, manifest, None if None in open_s else sum(open_s))
        if done else None,
        "does_not_prove": DOES_NOT_PROVE}
    body["headline"] = {"void": void, "confirm": conf and conf["status"],
                        "criteria_pass": None if not done else {
                            k: v["pass"] for k, v in body["criteria"].items()},
                        "report": str(root / "report.json")}
    bench.write_json(root / "report.json", body)
    return body


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m harness.decision_bench")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-suite")
    b.add_argument("family")
    for flag, kind in (("--rev", str), ("--since", str), ("--max-changed", int),
                       ("--negatives", int), ("--seed", int), ("--repo", str)):
        b.add_argument(flag, type=kind)
    b.add_argument("--out", required=True)
    for name in ("seal", "report", "run", "fit-policy", "confirm"):
        sp = sub.add_parser(name)
        sp.add_argument("--suite", required=True)
        if name in ("run", "confirm"):
            sp.add_argument("--split", required=True, choices=bench.SPLITS)
            sp.add_argument("--deadline-ms", type=int, default=2000)
            sp.add_argument("--seed", type=int, default=1709)
        if name in ("fit-policy", "confirm"):
            sp.add_argument("--arm", required=True)
    sub.choices["run"].add_argument("--arm", required=True, action="append")
    sub.choices["report"].add_argument("--gpu-rate", type=float)
    fit = sub.choices["fit-policy"]
    fit.add_argument("--act-on", action="append")
    # The flags keep select_threshold's names (section 5.4): --max-error is the
    # risk target, stored as the card's alpha; --alpha (or --delta) is the
    # confidence, stored as the card's delta.
    fit.add_argument("--max-error", dest="risk", type=float, default=.05)
    fit.add_argument("--alpha", "--delta", dest="confidence", type=float, default=.05)
    sub.choices["run"].add_argument("--random-coverage", type=float)
    sub.choices["confirm"].add_argument("--baseline", action="append")
    sub.choices["confirm"].add_argument("--diagnostic", action="store_true")
    return p


def _dispatch(a) -> dict:
    if a.command == "build-suite":
        params = {k: v for k, v in vars(a).items()
                  if k not in ("command", "family", "out") and v is not None}
        return {"manifest": str(bench.build_suite(a.family, a.out, **params))}
    if a.command == "seal":
        return {k: v for k, v in bench.seal(a.suite).items() if k != "leak"}
    if a.command == "run":
        return bench.run(a.suite, a.split, a.arm, deadline_ms=a.deadline_ms,
                         seed=a.seed, coverage=a.random_coverage)
    if a.command == "fit-policy":
        return bench.fit_policy(a.suite, a.arm, act_on=a.act_on, alpha=a.risk,
                                delta=a.confidence)
    if a.command == "confirm":
        need(a.split == "sealed", "confirm_reads_the_sealed_split_only")
        return confirm(a.suite, a.arm, baselines=a.baseline, diagnostic=a.diagnostic,
                       deadline_ms=a.deadline_ms, seed=a.seed)["headline"]
    return report(a.suite, gpu_rate=a.gpu_rate)["headline"]


def cli(argv=None) -> int:
    """``python -m harness.decision_bench``; exit 2 on a refusal."""
    args = _parser().parse_args(argv)
    try:
        result = _dispatch(args)
    except bench.BenchRefused as exc:
        print(json.dumps({"refused": exc.code}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, default=str))
    return 0

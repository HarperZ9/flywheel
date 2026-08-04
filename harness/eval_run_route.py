"""eval_run_route.py -- the eval-run surface behind the gateway's thin stubs.

Two handlers, both returning (body, http_code) in the gateway's own vocabulary:

  handle_eval_run    -- run a real eval through a real provider and seal the
                        outcome into an offline-verifiable receipt.
  handle_eval_verify -- re-check a receipt with the offline verifier.

The run is honest end to end: a deterministic slice of the code-domain task set
(pytest oracles that run OFFLINE, no network) is proposed to the chosen
endpoint's real model, each task is disposed by run_verified (the oracle
accepts, never the provider), and the results are sealed by eval_receipt. The
provider only proposes; the seal binds what actually happened. Credential and
endpoint errors surface with the SAME body/code shapes gateway.route_request
uses (404 unknown, 400 no credential, 502 provider failure), never a silent
local fallback.

The module keeps run_verified and make_endpoint_proposer as module-level names
so a test can substitute them and exercise the whole route with no real model.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .endpoint_registry import make_endpoint_proposer, unified_roster
from .eval_receipt import build_eval_receipt, emit_eval_receipt, verify_eval_receipt
from .oracle_registry import run_verified
from .task import load_task
from .tasks_lib import REGISTRY, materialize

# The eval run is over the code domain: pytest oracles that a stranger can
# re-run with no network and no GPU. That is what makes the receipt's outcome
# reproducible offline.
EVAL_DOMAIN = "code"
_DEFAULT_N = 3
_MAX_N = 5


def _now_iso() -> str:
    """UTC timestamp, timezone-aware. datetime.timezone.utc (never the 3.11
    datetime.UTC alias) so the module runs on Python 3.10."""
    return datetime.now(timezone.utc).isoformat()


def _clamp_n(raw: Any) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = _DEFAULT_N
    return max(1, min(n, _MAX_N))


def _select_specs(n: int) -> list:
    """The deterministic, offline-safe task slice. First-n of the curated
    code-task registry, so a run is reproducible: the same n selects the same
    tasks, and the dataset digest is stable across runs."""
    return list(REGISTRY[:n])


def _dataset_identity(specs: list) -> list[dict[str, str]]:
    """The task identity the receipt binds to (never the task bodies): id,
    oracle command, and prompt. Stable and sorted-serialized by the digest."""
    return [{"task_id": s.task_id, "oracle_cmd": s.oracle_cmd, "prompt": s.prompt}
            for s in specs]


def handle_eval_run(req: dict, run_root) -> tuple[dict, int]:
    """Run an eval and return the sealed receipt. (body, http_code).

    req: {"endpoint": <required>, "model": <optional str>, "n": <optional int,
    default 3, cap 5>}. The endpoint is credential-gated exactly as the router
    is; a run over an endpoint with no key present is refused honestly.
    """
    endpoint = str(req.get("endpoint") or "").strip()
    if not endpoint:
        return {"error": "provide a non-empty 'endpoint'"}, 400
    model = req.get("model")
    model = str(model).strip() if isinstance(model, str) and model.strip() else None
    n = _clamp_n(req.get("n", _DEFAULT_N))

    # Credential-presence gate -- mirror gateway.route_request's shapes exactly.
    roster = unified_roster()
    entry = next((e for e in roster.get("endpoints", [])
                  if e.get("name") == endpoint), None)
    if entry is None:
        return {"error": f"unknown endpoint {endpoint!r}",
                "usable": roster.get("usable_names", [])}, 404
    if entry.get("credential") == "absent":
        return {"error": f"endpoint {endpoint!r} has no credential present; set "
                f"its API key in the environment (presence only, never read "
                f"here)", "credential": "absent"}, 400

    try:
        prop = make_endpoint_proposer(endpoint, model=model or None)
    except Exception as e:  # noqa: BLE001 -- an unbuildable proposer is a 502
        return {"error": f"cannot build a proposer for {endpoint!r}: {e}"}, 502

    specs = _select_specs(n)
    work_base = Path(run_root) / "eval" / "work"
    started = _now_iso()
    results: list[dict[str, Any]] = []
    model_ref = getattr(prop, "model_ref", "") or (model or endpoint)
    try:
        for spec in specs:
            task_dir = work_base / spec.task_id
            materialize(spec, task_dir)
            task = load_task(task_dir, workdir=task_dir / "wd")
            ev = run_verified(task, prop, domain=EVAL_DOMAIN,
                              envelopes_dir=str(work_base / "envelopes"))
            loop = getattr(ev, "loop", None)
            env = getattr(loop, "envelope", None) if loop is not None else None
            if env is not None and getattr(env, "model_ref", ""):
                model_ref = env.model_ref
            results.append({"task_id": spec.task_id,
                            "verdict": getattr(ev, "verdict", ""),
                            "accepted": getattr(ev, "accepted", False)})
    except Exception as e:  # noqa: BLE001 -- a provider call failure is a 502
        return {"error": f"provider call failed: {e}", "endpoint": endpoint}, 502

    finished = _now_iso()
    run_id = f"eval-{endpoint}-{os.urandom(4).hex()}"
    receipt = build_eval_receipt(
        run_id=run_id, endpoint=endpoint, model_ref=model_ref,
        tasks=_dataset_identity(specs),
        config={"n": n, "domain": EVAL_DOMAIN, "selection": "first-n"},
        judge=f"{EVAL_DOMAIN} oracle (pytest, offline)",
        results=results, started_utc=started, finished_utc=finished)

    receipt_dir = Path(run_root) / "eval"
    written = emit_eval_receipt(receipt, receipt_dir)
    # receipt_file is a BARE filename, never an absolute path -- a receipt is
    # portable, and its on-disk location is the running host's business.
    receipt_file = written.name if written is not None else ""
    return {"schema": "flywheel.eval-run/v1", "endpoint": endpoint,
            "model_ref": model_ref, "n": str(n), "results": results,
            "receipt": receipt, "receipt_file": receipt_file}, 200


def handle_eval_verify(req: dict) -> tuple[dict, int]:
    """Re-check a receipt offline. Always 200: the verdict itself carries the
    good/bad news (MATCH / TAMPERED / UNVERIFIABLE), so a corrupted receipt is a
    first-class result, not an HTTP error."""
    receipt = req.get("receipt")
    return verify_eval_receipt(receipt if isinstance(receipt, dict) else None), 200

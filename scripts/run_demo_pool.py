"""run_demo_pool.py -- the fill driver: 60 instances, K=4, one fingerprint.

Builds the frozen instance set for one family (project-docs/prereg/
2026-07-26-size-invariant-verification.md, sections 2-4), renders each
instance through demo_prompt.py's template, and calls harness/pool.py's
`fill` against a live Ollama rung. harness/pool.py is never modified: this is
the caller, not the cache.

FROZEN, read from the prereg and honored exactly:
  - 60 instances per family: difficulties 1..5, twelve per band.
  - seeds 0..59, assigned to bands in ascending blocks of twelve
    (seed // 12 + 1 == difficulty). Not a range that could silently widen.
  - K = 4 candidates per instance per rung, no early stopping (pool.fill's
    own contract already enforces the no-early-stopping half).
  - one fingerprint held identical across rungs of the same run.

NOT frozen by the prereg text, and decided here (flagged in the delivery
report as guesses, not read facts):
  - the K=4 (seed, temperature) schedule beyond slot 0. The prereg pins only
    slot 0 to seed 0 / temperature 0 (section 4: "single | none, slot 0 at
    temperature 0", and harness/pool_arms.py's `single` docstring says the
    same). Slots 1-3 use this repo's own existing seed list
    (harness/adaptive_select.py's _SEEDS, first three non-zero entries) and a
    temperature ladder (its _HOT_TEMPS prefix) rather than inventing new
    numbers, but the prereg does not pin these values.
  - max_new_tokens: not stated anywhere in the prereg or pool.py.
  - model_digest: the prereg says "from /api/show and /api/version", but
    /api/show (verified live against Ollama 0.32.3, and independently noted
    in tests/test_determinism_pins.py) exposes no digest field at all. The
    per-model digest lives in /api/tags instead, so this module calls that
    third endpoint for model_digest specifically.
  - the short family keys "zarankiewicz" / "rectilinear_crossing" used for
    --family: these are ZarankiewiczOracle.family and CrossingOracle.family
    exactly (harness/certificates/zarankiewicz.py,
    harness/certificates/crossing.py), not the prereg's longer criterion_id
    strings, chosen because the smoke-test invocation this driver must serve
    uses the short form ("--family zarankiewicz").
  - on-disk path sanitization: a rung tag like "qwen2.5:0.5b" contains a
    colon, which Windows refuses as a path component. The literal rung string
    still goes into the fingerprint's model_ref and the run manifest; only
    the directory name is sanitized.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.pool import fill, make_fingerprint  # noqa: E402
from harness.certificates.generators import zarankiewicz_instance  # noqa: E402
from harness.certificates.crossing_generator import crossing_instance  # noqa: E402
from demo_prompt import render_prompt, template_sha256  # noqa: E402
from demo_proposer import OllamaProposer, default_base_url  # noqa: E402

SCHEMA = "flywheel.demo-pool-run/v1"

FAMILIES = {
    "zarankiewicz": {"criterion_id": "zarankiewicz.z_2_2.v1",
                     "generator": zarankiewicz_instance},
    "rectilinear_crossing": {"criterion_id": "rectilinear_crossing.count.v1",
                             "generator": crossing_instance},
}

INSTANCES_PER_BAND = 12
N_DIFFICULTIES = 5
TOTAL_INSTANCES = INSTANCES_PER_BAND * N_DIFFICULTIES              # 60, frozen

K = 4                                                                # frozen
# Slot 0 is frozen (seed 0, temperature 0). Slots 1-3: see module docstring.
SEEDS = [0, 42, 137, 7]
TEMPERATURES = [0.0, 0.2, 0.35, 0.5]
MAX_NEW_TOKENS = 2048

DEFAULT_OUT = REPO / "artifacts" / "pool"

_UNSAFE_PATH_CHARS = '<>:"/\\|?*'

DOES_NOT_PROVE = [
    "NOT_PROVES_ACCEPTANCE: filling a pool caches candidates. No certificate "
    "here has been submitted through an oracle's accept path; well-formedness "
    "and PASS/FAIL are a separate, later step.",
    "NOT_PROVES_THIS_IS_THE_CONFIRMATORY_RUN: that is exactly what the "
    "pilot/confirmatory stamp on this manifest exists to make unambiguous.",
]


class DemoPoolError(ValueError):
    """A refusal at the driver level: bad family, bad flags, bad limit."""


def build_instances(family: str) -> list[dict]:
    """The 60 frozen instances: seeds 0..59 ascending, twelve per band."""
    if family not in FAMILIES:
        raise DemoPoolError(
            f"unknown family {family!r}; supported are {sorted(FAMILIES)}")
    generator = FAMILIES[family]["generator"]
    return [generator(seed=seed, difficulty=seed // INSTANCES_PER_BAND + 1)
            for seed in range(TOTAL_INSTANCES)]


def task_id_for(family: str, instance: dict) -> str:
    """Rung-independent: the same 60 ids for every rung of one family, so
    pools from different rungs stay joinable by task_id."""
    return f"{family}.seed{instance['seed']:02d}.d{instance['difficulty']}"


def build_tasks(family: str, instances: list[dict]) -> list[dict]:
    return [{"task_id": task_id_for(family, inst),
             "prompt": render_prompt(family, inst),
             "max_new_tokens": MAX_NEW_TOKENS} for inst in instances]


def safe_path_component(name: str) -> str:
    """Windows forbids : < > " / \\ | ? * in one path component (colon also
    means drive letter / alternate data stream). "qwen2.5:0.5b" is not a
    legal directory name; sanitize for disk only, never for the fingerprint."""
    return "".join("_" if c in _UNSAFE_PATH_CHARS else c for c in name)


def out_dir_for(out_base, family: str, rung: str) -> Path:
    return Path(out_base) / family / safe_path_component(rung)


def _default_fetch(base_url: str):
    def fetch(path: str, payload: dict | None = None) -> dict:
        url = base_url.rstrip("/") + path
        if payload is None:
            request = urllib.request.Request(url)
        else:
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    return fetch


def _model_digest(tags_doc: dict, model: str) -> str | None:
    """/api/tags carries a "digest" per served model; /api/show does not
    (verified against a live 0.32.3 server -- see module docstring)."""
    for entry in (tags_doc.get("models") or []):
        if entry.get("name") == model or entry.get("model") == model:
            d = entry.get("digest")
            return f"sha256:{d}" if d else None
    return None


def build_fingerprint(base_url: str, model: str, template_sha: str,
                      fetch=None) -> dict:
    fetch = fetch or _default_fetch(base_url)
    version_doc = fetch("/api/version") or {}
    show_doc = fetch("/api/show", {"model": model}) or {}
    tags_doc = fetch("/api/tags") or {}
    details = show_doc.get("details") or {}
    return make_fingerprint(
        model_ref=model,
        model_digest=_model_digest(tags_doc, model),
        engine="ollama",
        engine_version=version_doc.get("version"),
        quantization=details.get("quantization_level"),
        k=K, seeds=list(SEEDS), temperatures=list(TEMPERATURES),
        max_new_tokens=MAX_NEW_TOKENS, prompt_template_sha256=template_sha)


def build_run_manifest(*, family: str, rung: str, confirmatory: bool,
                       pilot: bool, limit, reason, n_instances: int) -> dict:
    return {"schema": SCHEMA, "family": family,
           "criterion_id": FAMILIES[family]["criterion_id"], "rung": rung,
           "confirmatory": confirmatory, "pilot": pilot,
           "limit": limit if limit is not None else None,
           "pilot_reason": reason if pilot else None,
           "n_instances": n_instances, "does_not_prove": list(DOES_NOT_PROVE)}


def run_fill(*, family: str, rung: str, out_base, limit=None,
            confirmatory: bool, pilot: bool, reason=None, base_url=None,
            fetch=None, proposer=None) -> dict:
    """Build the instance set, fill the pool, stamp the run manifest.

    Every ambiguity the stopping rule forbids is refused here rather than
    upstream in argparse, so a direct caller (a test, or another script)
    cannot bypass it either.
    """
    if family not in FAMILIES:
        raise DemoPoolError(
            f"unknown family {family!r}; supported are {sorted(FAMILIES)}")
    if confirmatory == pilot:
        raise DemoPoolError(
            "exactly one of confirmatory or pilot must be set; an unlabeled "
            "run is exactly the ambiguity the prereg's stopping rule forbids")
    if limit is not None and not pilot:
        raise DemoPoolError("limit is only valid together with pilot=True")
    if limit is not None and limit < 1:
        raise DemoPoolError("limit must be a positive integer")

    instances = build_instances(family)
    if limit is not None:
        instances = instances[:limit]

    template_sha = template_sha256(family)
    tasks = build_tasks(family, instances)

    base_url = base_url or default_base_url()
    fingerprint = build_fingerprint(base_url, rung, template_sha, fetch=fetch)
    proposer = proposer or OllamaProposer(rung, host=base_url)

    out_dir = out_dir_for(out_base, family, rung)
    doc = fill(tasks, proposer, fingerprint, out_dir)

    manifest = build_run_manifest(
        family=family, rung=rung, confirmatory=confirmatory, pilot=pilot,
        limit=limit, reason=reason, n_instances=len(tasks))
    Path(out_dir, "run_manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    return {"pool": doc, "manifest": manifest, "out_dir": str(out_dir)}


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--family", required=True, choices=sorted(FAMILIES))
    ap.add_argument("--rung", required=True,
                    help="Ollama model tag as served, e.g. qwen2.5:0.5b")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="pool output base directory (default artifacts/pool)")
    ap.add_argument("--limit", type=int, default=None,
                    help="pilot only: cap the instance count for a dry run")
    ap.add_argument("--pilot-reason", default=None,
                    help="pilot only: why this is a pilot, not the "
                         "confirmatory run (a default is generated if omitted)")
    ap.add_argument("--base-url", default=None,
                    help="defaults to $OLLAMA_HOST, else 127.0.0.1:11434")
    ap.add_argument("--json", dest="as_json", action="store_true")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--confirmatory", action="store_true",
                       help="the ONE confirmatory run the stopping rule allows")
    group.add_argument("--pilot", action="store_true",
                       help="a mechanical dry run; never the confirmatory run")
    return ap


def _default_pilot_reason(limit) -> str:
    base = "mechanical pilot run, not the confirmatory run"
    return base if limit is None else f"{base}; --limit {limit}"


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    reason = args.pilot_reason
    if args.pilot and not reason:
        reason = _default_pilot_reason(args.limit)

    try:
        result = run_fill(
            family=args.family, rung=args.rung, out_base=Path(args.out),
            limit=args.limit, confirmatory=args.confirmatory, pilot=args.pilot,
            reason=reason, base_url=args.base_url)
    except DemoPoolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    manifest = result["manifest"]
    if args.as_json:
        print(json.dumps(manifest, indent=1, sort_keys=True))
    else:
        print(f"filled {manifest['n_instances']} task(s) for "
             f"{manifest['family']} @ {manifest['rung']} -> {result['out_dir']}")
        print(f"pilot={manifest['pilot']} confirmatory={manifest['confirmatory']}"
             + (f" reason={manifest['pilot_reason']!r}" if manifest['pilot'] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

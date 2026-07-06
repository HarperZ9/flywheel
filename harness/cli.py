"""cli.py — the runner. Invokes the harness on a task and emits the envelope.

Dogfooding: turns the harness from a testable library into a usable tool.
  py -m harness.cli <task_dir> [--search] [--boot ROOT] [--cache DIR] [--policy]

Single-candidate by default; --search runs the verified_inference arm (best-of-N
+ voice-cap). --boot hydrates from a workspace root. --cache enables the M5
receipt cache. Prints the verdict; writes the envelope to --envelopes-dir.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .task import load_task
from .loop import run_loop
from .proposer import StubProposer, ServeProposer
from .oracle import PytestOracle
from .cache import ReceiptCache
from .eval import VERIFIED_INFERENCE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="harness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_dir", help="task directory (contains task.json + skeleton/)")
    ap.add_argument("--search", action="store_true",
                    help="run the verified_inference arm (best-of-N + voice-cap)")
    ap.add_argument("--boot", default=None, metavar="ROOT",
                    help="hydrate from a workspace root (boot stage)")
    ap.add_argument("--boot-budget", type=int, default=1500)
    ap.add_argument("--cache", default=None, metavar="DIR",
                    help="enable the M5 receipt cache at this dir")
    ap.add_argument("--serve", default=None, metavar="URL",
                    help="use the local model server (default: stub proposer)")
    ap.add_argument("--envelopes-dir", default="envelopes")
    ap.add_argument("--no-witness", action="store_true",
                    help="skip the witness re-check (faster, less rigorous)")
    args = ap.parse_args(argv)

    task = load_task(args.task_dir)
    proposer = (ServeProposer(args.serve) if args.serve
                else StubProposer("def f():\n    pass\n", model_ref="cli-stub"))
    oracle = PytestOracle()
    cache = ReceiptCache(args.cache) if args.cache else None
    result = run_loop(
        task, proposer, oracle,
        envelopes_dir=args.envelopes_dir,
        witness_recheck=not args.no_witness,
        boot_root=args.boot, boot_budget=args.boot_budget,
        cache=cache,
        search=(VERIFIED_INFERENCE if args.search else None))

    env = result.envelope
    print(json.dumps({
        "task_id": env.task_id,
        "verdict": env.verdict,
        "accepted": result.accepted,
        "cache_hit": result.cache_hit,
        "model_ref": env.model_ref,
        "oracle": env.oracle,
        "oracle_output_hash": env.oracle_output_hash,
        "chain_stages": [s["stage"] for s in env.chain],
        "chain_head_hash": env.chain[-1].get("receipt_hash") if env.chain else None,
        "elapsed_s": round(result.elapsed_s, 3),
    }, indent=2))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    sys.exit(main())

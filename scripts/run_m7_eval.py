"""run_m7_eval.py — the M7 eval runner. Fires when the trained model lands.

Measures HARNESS LIFT on the held-out task set.
Default mode runs local verified_inference vs local single_shot, plus flat-N and no-search ablations.
Use --frontier to add an external frontier single-shot baseline and compare verified_inference against it.
Use --frontier-all (or --frontier-providers) to compare against the full existing endpoint ladder
across all configured providers/modes.

Usage (real, after training + `serve.py` with ADAPTER_PATH set to the checkpoint):
    py scripts/run_m7_eval.py --serve http://127.0.0.1:8765 --out m7_scorecard.json
Dry-run (no GPU, proves the runner end-to-end with reference solutions):
    py scripts/run_m7_eval.py --dry-run --out /tmp/m7_dry.json
Frontier-mode dry-run:
    py scripts/run_m7_eval.py --dry-run --frontier --out /tmp/m7_frontier_dry.json
Pin/compare against a prior scorecard:
    py scripts/run_m7_eval.py ... --pinned prior_scorecard.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.eval import (run_eval, compare, save_scorecard, load_scorecard,
                         delta_vs_pinned, ArmConfig, SINGLE_SHOT,
                         VERIFIED_INFERENCE, FLAT_N, NO_SEARCH)
from harness.oracle import PytestOracle
from harness.proposer import ServeProposer, StubProposer, ProposerOutput, prompt_hash
from harness.extract import extract_code
from harness.endpoints import build_endpoints, PROVIDERS
from harness.tasks_lib import REGISTRY, materialize_all
from harness.tasks_hard import HARD_REGISTRY
from harness.tasks_expert import EXPERT_REGISTRY
from harness.task import load_task
from harness.providers import make_proposer, REGISTRY as MODEL_REGISTRY

FRONTIER_SINGLE_SHOT = ArmConfig(name="frontier_single_shot", n_candidates=1,
                                 label="frontier baseline analog")
ARMS = [SINGLE_SHOT, VERIFIED_INFERENCE, FLAT_N, NO_SEARCH]


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _sanitize(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name.lower())


class EndpointProposer:
    """Adapter: any endpoint backend becomes a Proposer for eval harness comparisons."""

    def __init__(self, backend):
        self.backend = backend
        self.model_ref = backend.name

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        gen = self.backend.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=max_new_tokens,
            temperature=temperature,
            seed=seed,
        )
        return ProposerOutput(
            text=extract_code(gen["text"]),
            model_ref=gen.get("model_ref", self.model_ref),
            seed=gen.get("seed", seed),
            prompt_hash=prompt_hash(prompt),
            cache="frontier",
        )


def _registry(tier: str):
    return {"expert": EXPERT_REGISTRY, "hard": HARD_REGISTRY}.get(tier, REGISTRY)


def build_task_set(workroot: Path, n: int, tier: str = "easy"):
    dirs = materialize_all(_registry(tier)[:n], workroot / "m7-tasks")
    return [load_task(d) for d in dirs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default="http://127.0.0.1:8765")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hard", action="store_true", help="use the harder held-out set")
    ap.add_argument("--expert", action="store_true", help="use the EXPERT set (uplift headroom)")
    ap.add_argument("--n-tasks", type=int, default=0)
    ap.add_argument("--out", default="m7_scorecard.json")
    ap.add_argument("--pinned", default="")
    ap.add_argument("--workroot", default=str(Path(__file__).parent.parent / ".m7-run"))
    ap.add_argument("--frontier", action="store_true",
                    help="compare verified_inference against frontier single-shot")
    ap.add_argument("--frontier-provider", default="codex",
                    help="provider name for frontier proposer (default: codex)")
    ap.add_argument("--frontier-model", default="gpt-5.3-codex-spark",
                    help="model name for frontier baseline")
    ap.add_argument("--frontier-base-url", default="",
                    help="override base URL for frontier proposer")
    ap.add_argument("--frontier-all", action="store_true",
                    help="use all configured providers/modes from endpoints.py as frontier arms")
    ap.add_argument("--frontier-providers", default="",
                    help="comma list of providers for frontier-mode (implies multi-backend frontier)")
    ap.add_argument("--frontier-modes", default="plan,api,provider,cloud",
                    help="comma list of endpoint modes for frontier backend expansion")
    ap.add_argument("--local", action="store_true",
                    help="compare local-provider single-shot baselines")
    ap.add_argument("--local-provider", default="",
                    help="comma list of local providers for local baseline sweep "
                         "(default: all local providers in providers.REGISTRY plus 'serve')")
    ap.add_argument("--local-model", default="",
                    help="override model name for all local baseline providers")
    ap.add_argument("--local-primary", default="serve",
                    help="local proposer for verified_inference (default: serve)")
    a = ap.parse_args()

    tier = "expert" if a.expert else ("hard" if a.hard else "easy")
    n = a.n_tasks or len(_registry(tier))
    workroot = Path(a.workroot)
    task_set = build_task_set(workroot, n, tier=tier)

    frontier_arms: list[ArmConfig] = []
    frontier_proposers: dict[str, object] = {}
    frontier_meta: dict[str, str] = {}
    frontier_modes = tuple(_split_csv(a.frontier_modes))
    if not frontier_modes:
        frontier_modes = ("plan", "api", "provider", "cloud")

    local_arms: list[ArmConfig] = []
    local_proposers: dict[str, object] = {}
    local_meta: dict[str, str] = {}
    local_provider_names = [p for p, spec in MODEL_REGISTRY.items() if spec.local]
    if "serve" not in local_provider_names:
        local_provider_names.append("serve")
    if not local_provider_names:
        local_provider_names = ["serve"]

    if a.local:
        local_providers = _split_csv(a.local_provider) or local_provider_names
        for pname in local_providers:
            if pname == "serve":
                local_model = a.local_model or "14b-cpt-adapter"
                arm_name = f"local_{_sanitize(pname)}"
                local_arms.append(ArmConfig(
                    name=arm_name,
                    n_candidates=1,
                    label=f"local ({pname})",
                ))
                local_meta[arm_name] = f"{pname}:{local_model}"
                if not a.dry_run:
                    local_proposers[arm_name] = ServeProposer(
                        base_url=a.serve,
                        model_ref=local_model)
                else:
                    local_proposers[arm_name] = StubProposer(
                        "pass\n", model_ref=local_meta[arm_name])
                continue

            if pname not in MODEL_REGISTRY:
                known_local = ", ".join(sorted(set(MODEL_REGISTRY) | {"serve"}))
                raise ValueError(f"unknown local provider {pname!r} (known: {known_local})")
            if not MODEL_REGISTRY[pname].local:
                raise ValueError(f"{pname!r} is not local; pass --frontier for remote providers")
            arm_name = f"local_{_sanitize(pname)}"
            local_arms.append(ArmConfig(
                name=arm_name,
                n_candidates=1,
                label=f"local ({pname})",
            ))
            local_model = a.local_model or MODEL_REGISTRY[pname].default_model
            local_meta[arm_name] = f"{pname}:{local_model}"
            if not a.dry_run:
                local_proposers[arm_name] = make_proposer(
                    pname, model=local_model or None, base_url=None
                )
            else:
                local_proposers[arm_name] = StubProposer("pass\n", model_ref=local_meta[arm_name])

    if a.frontier and not a.dry_run and (a.frontier_all or a.frontier_providers):
        providers = _split_csv(a.frontier_providers) or None
        backends = build_endpoints(providers=providers, modes=frontier_modes)
        if not backends:
            raise ValueError(
                "frontier requested but no configured endpoint backends found; "
                "set provider credentials or run with --frontier-providers and --dry-run")
        for backend in backends:
            arm_name = f"frontier_{_sanitize(backend.name)}"
            frontier_arms.append(ArmConfig(
                name=arm_name,
                n_candidates=1,
                label=f"frontier ({backend.name})",
            ))
            frontier_proposers[arm_name] = EndpointProposer(backend)
            backend_model = getattr(backend, "model", backend.name.split("-", 1)[0])
            frontier_meta[arm_name] = f"{backend.name}:{backend_model}"

    if a.frontier and not frontier_arms and not a.dry_run and not a.frontier_all and not a.frontier_providers:
        p = make_proposer(
            a.frontier_provider,
            model=a.frontier_model,
            base_url=a.frontier_base_url or None
        )
        frontier_arms.append(FRONTIER_SINGLE_SHOT)
        frontier_proposers[FRONTIER_SINGLE_SHOT.name] = p
        frontier_meta[FRONTIER_SINGLE_SHOT.name] = f"{a.frontier_provider}:{a.frontier_model}"

    if a.frontier and a.dry_run and not frontier_arms:
        if a.frontier_all or a.frontier_providers:
            dry_providers = _split_csv(a.frontier_providers) or list(PROVIDERS)
            for pname in dry_providers:
                for mode in frontier_modes:
                    arm_name = f"frontier_{_sanitize(f'{pname}-{mode}')}"
                    frontier_arms.append(ArmConfig(
                        name=arm_name,
                        n_candidates=1,
                        label=f"frontier ({pname}-{mode})",
                    ))
                    frontier_meta[arm_name] = f"{pname}:{a.frontier_model}"
        else:
            frontier_arms.append(FRONTIER_SINGLE_SHOT)
            frontier_meta[FRONTIER_SINGLE_SHOT.name] = f"{a.frontier_provider}:{a.frontier_model}"
            frontier_proposers[FRONTIER_SINGLE_SHOT.name] = StubProposer(
                "pass\n",
                model_ref=frontier_meta[FRONTIER_SINGLE_SHOT.name]
            )
        # dry runs never call the live API/backends
        frontier_proposers = {name: StubProposer("pass\n", model_ref=meta)
                             for name, meta in frontier_meta.items()}

    if a.dry_run:
        ref = {s.task_id: s.solution for s in _registry(tier)}

        def proposer_for(arm, task):
            if arm.name in local_proposers:
                return local_proposers[arm.name]
            return StubProposer(ref.get(task.task_id, "pass\n"), model_ref="dry-run(reference)")

        model_ref = "dry-run(reference)"
    else:
        if a.local_primary == "serve":
            local_proposer = ServeProposer(
                base_url=a.serve,
                model_ref=a.local_model or "14b-cpt-adapter")
        else:
            if a.local_primary not in MODEL_REGISTRY:
                raise ValueError(f"unknown local-primary provider {a.local_primary!r} (known: {', '.join(MODEL_REGISTRY)})")
            if not MODEL_REGISTRY[a.local_primary].local:
                raise ValueError(f"--local-primary requires a local provider, got {a.local_primary!r}")
            local_proposer = make_proposer(
                a.local_primary, model=a.local_model or None
            )

        def proposer_for(arm, task):
            if arm.name in local_proposers:
                return local_proposers[arm.name]
            if arm.name in frontier_proposers:
                proposer = frontier_proposers[arm.name]
                if isinstance(proposer, StubProposer):
                    return proposer
                return proposer
            return local_proposer

        model_ref = local_proposer.model_ref

    def oracle_for(task):
        return PytestOracle()

    arms = ARMS.copy()
    arms.extend(frontier_arms)
    arms.extend(local_arms)

    reports = run_eval(arms, task_set, proposer_for, oracle_for)
    print("=== M7 eval (harness lift on the held-out set) ===")
    for name, r in reports.items():
        print("  " + r.summary())

    if frontier_arms:
        for arm in frontier_arms:
            verdict = compare(reports, baseline=arm.name, candidate=VERIFIED_INFERENCE.name)
            print(f"  verdict (verified_inference >= {arm.name}): {verdict}")
    if local_arms:
        for arm in local_arms:
            verdict = compare(reports, baseline=arm.name, candidate=VERIFIED_INFERENCE.name)
            print(f"  verdict (verified_inference >= {arm.name}): {verdict}")
    else:
        verdict = compare(reports, baseline=SINGLE_SHOT.name, candidate=VERIFIED_INFERENCE.name)
        print(f"  verdict (verified_inference >= {SINGLE_SHOT.name}): {verdict}")

    meta = {"model_ref": model_ref, "n_tasks": len(task_set),
            "note": ("frontier single-shot baseline comparison"
                     if a.frontier else
                     "harness lift vs single-shot of the SAME model")}
    if a.frontier:
        meta["frontier_mode"] = "multi-endpoint" if frontier_proposers and len(frontier_arms) > 1 else "single"
        meta["frontier_arms"] = [arm.name for arm in frontier_arms]
        meta["frontier_model_refs"] = frontier_meta
        if frontier_meta and len(frontier_arms) == 1:
            only = frontier_arms[0]
            meta["frontier_model_ref"] = frontier_meta[only.name]
            if only.name == FRONTIER_SINGLE_SHOT.name:
                meta["frontier_provider"] = a.frontier_provider
    if a.local:
        meta["local_mode"] = "sweep"
        meta["local_arms"] = [arm.name for arm in local_arms]
        meta["local_model_refs"] = local_meta

    save_scorecard(a.out, reports, meta=meta)
    print(f"  scorecard -> {a.out}")

    if a.pinned and Path(a.pinned).exists():
        d = delta_vs_pinned(reports, load_scorecard(a.pinned))
        print(f"  vs pinned {a.pinned}: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

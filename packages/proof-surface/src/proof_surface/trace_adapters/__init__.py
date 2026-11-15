"""Trace-to-receipt adapters: real observability exports -> normalized trace.

Keep your existing observability stack; attach receipts. These adapters flatten
vendor trace exports (OpenTelemetry OTLP/JSON, LangSmith/Langfuse-style run trees)
into the normalized trace shape proof_surface.agent_action.import_trace ingests,
so an agent-action proof packet can be built from data teams already collect.

The ``frameworks`` adapters go one step further: they wrap eval/observability
incumbents (the pass 0064 adapter matrix) as evidence inputs and declare, via
``NON_INFERABLE``, the Telos proof-layer fields those exports cannot supply.
``ADAPTER_COVERAGE`` is the enforced completeness map: every priority-5 incumbent
must have a covering adapter (see ``uncovered_priority5``).
"""

from __future__ import annotations

from typing import Any, Callable

from .frameworks import (
    NON_INFERABLE,
    import_arize_phoenix_span,
    import_braintrust_experiment,
    import_dvc_stage,
    import_helicone_request,
    import_mlflow_run,
    import_promptfoo_eval,
    import_slsa_provenance,
    import_wandb_artifact,
    import_wandb_weave_call,
)
from .otel import normalize_otel
from .run_tree import normalize_run_tree

# Pass 0064 ranks these incumbents priority 5: each MUST have a covering adapter.
PRIORITY5_INCUMBENTS = [
    "OpenTelemetry",
    "LangSmith",
    "Langfuse",
    "Arize Phoenix",
    "Braintrust",
]

# Every incumbent observability/eval surface -> the proof_surface adapter that
# preserves its native refs. Trace-shape incumbents map to the trace normalizer
# that feeds import_trace; eval/artifact incumbents map to an evidence adapter.
ADAPTER_COVERAGE: dict[str, Callable[[Any], Any]] = {
    "OpenTelemetry": normalize_otel,
    "LangSmith": normalize_run_tree,
    "Langfuse": normalize_run_tree,
    "Arize Phoenix": import_arize_phoenix_span,
    "Braintrust": import_braintrust_experiment,
    "MLflow": import_mlflow_run,
    "W&B Weave": import_wandb_weave_call,
    "W&B Artifacts": import_wandb_artifact,
    "promptfoo": import_promptfoo_eval,
    "Helicone": import_helicone_request,
    "DVC": import_dvc_stage,
    "SLSA": import_slsa_provenance,
}


def uncovered_priority5() -> list[str]:
    """Priority-5 incumbents (pass 0064) with no covering adapter. [] iff complete."""
    return [tool for tool in PRIORITY5_INCUMBENTS if ADAPTER_COVERAGE.get(tool) is None]


__all__ = [
    "normalize_otel",
    "normalize_run_tree",
    "NON_INFERABLE",
    "PRIORITY5_INCUMBENTS",
    "ADAPTER_COVERAGE",
    "uncovered_priority5",
    "import_mlflow_run",
    "import_wandb_artifact",
    "import_wandb_weave_call",
    "import_slsa_provenance",
    "import_braintrust_experiment",
    "import_arize_phoenix_span",
    "import_promptfoo_eval",
    "import_helicone_request",
    "import_dvc_stage",
]

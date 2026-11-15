"""Best-effort demo -- not runtime-verified by author.

End-to-end walkthrough of the agent-routing-kit public API.

Run from the repository root with the package installed (`pip install -e .`)
or directly from source:

    PYTHONPATH=src python examples/demo.py
"""

from agent_routing_kit import (
    Capability,
    default_capabilities,
    estimate_context,
    route_task,
)


def main() -> int:
    # 1. Route a public task and print the Markdown summary.
    public = route_task("write tests and docs for a small Python CLI")
    print("== Public route (Markdown) ==")
    print(public.to_markdown())
    print("primary:", public.primary.name if public.primary else None)
    print()

    # 2. A task that touches private/restricted lanes: omitted by default,
    #    then opted in via include_private=True.
    sensitive_task = "design a frontend dashboard with private broker credentials"
    default_route = route_task(sensitive_task)
    print("== Sensitive task, default (private omitted) ==")
    print("excluded_risk_counts:", default_route.excluded_risk_counts)
    print(default_route.to_markdown())
    print()

    included_route = route_task(sensitive_task, include_private=True)
    print("== Sensitive task, include_private=True ==")
    print("matched names:", [cap.name for cap, _ in included_route.matches])
    print()

    # 3. JSON-friendly dict output and a tightened max_results.
    research = route_task(
        "research and compare two papers, summarize",
        max_results=2,
    )
    print("== Research route (to_dict) ==")
    print(research.to_dict())
    print()

    # 4. Estimate a context budget for some task text.
    budget = estimate_context("some model-bound context", max_tokens=8000)
    print("== Context budget ==")
    print(budget.to_dict())
    print("status:", budget.status)
    print()

    # 5. Route against a custom capability catalog instead of the default one.
    custom_catalog = default_capabilities() + (
        Capability(
            name="data-pipeline",
            domain="engineering",
            description="ETL jobs, batch processing, and scheduled data flows.",
            keywords=("etl", "pipeline", "batch", "ingest", "schedule"),
        ),
    )
    custom = route_task("build an etl pipeline to ingest data", capabilities=custom_catalog)
    print("== Custom catalog route ==")
    print("primary:", custom.primary.name if custom.primary else None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

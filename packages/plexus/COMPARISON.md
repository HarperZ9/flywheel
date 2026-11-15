# plexus vs the field

Honest positioning. plexus is young (0.2.0) and does not try to be an execution
engine. It occupies one layer the mature tools skip: **decentralized capability
discovery and wiring**. This page says where it wins and where it does not.

## The class

| System | What it is | Where it lives |
|---|---|---|
| **MCP** | A protocol for a server to expose tools to an agent | Tool discovery, per server |
| **LangGraph** | An imperative graph runtime for agent workflows | Execution + state |
| **LangChain (LCEL)** | Composable chains of calls | Execution + ecosystem |
| **Dagster / Airflow** | Typed data-pipeline DAGs with lineage | Execution + observability |
| **CrewAI / AutoGen** | Agent-role orchestration | Execution + conversation |
| **plexus** | Discovers the data-flow graph across independent tools | Discovery + wiring |

## Feature matrix

| Capability | MCP | LangGraph | Dagster | CrewAI | **plexus** |
|---|:--:|:--:|:--:|:--:|:--:|
| Decentralized: each tool ships its own contract | ~ | no | no | no | **yes** |
| Producer→consumer wiring from declared I/O | no | manual | manual | no | **auto** |
| Edges cite the code that produces them | no | no | ~ | no | **yes** |
| Honest orphans (unmet inputs / dead outputs) | no | no | ~ | no | **yes** |
| Feedback loops surfaced, not linearized | n/a | n/a | no | no | **yes** |
| Cross-language / cross-runtime (JSON manifests) | yes | no | no | no | **yes** |
| Graph visualization | ~ | yes | yes | ~ | **yes** |
| Plan → runnable script | no | n/a | n/a | no | **yes** |
| **Executes the pipeline** | n/a | **yes** | **yes** | **yes** | **no** |
| Retries / error handling / observability | n/a | **yes** | **yes** | ~ | **no** |
| State / memory / streaming | n/a | **yes** | ~ | **yes** | **no** |
| Mature ecosystem / integrations | growing | **large** | **large** | growing | **new** |

## Where plexus wins

The mature orchestrators all require **you** to author the graph: you already
know that tool A's output feeds tool B, and you wire it. plexus inverts that.
Each tool declares only *its own* emits and consumes, in a plain JSON manifest,
and plexus **derives** the cross-tool graph. No central author holds the whole
picture, so a tool can be added or a team can ship a manifest without editing a
shared pipeline definition. And every edge it draws cites the `file:function`
that produces the artifact, so the wiring is checkable, not asserted. Nobody else
in the class does decentralized, evidence-cited discovery.

## Where plexus does not win (yet)

It does not execute anything. LangGraph, Dagster, and CrewAI run the pipeline,
retry failures, and stream state; plexus emits a runnable script and stops there
by design. It has no observability layer and a brand-new ecosystem.

## The honest thesis

plexus is not "a better LangGraph." It is the **discovery layer that sits above
an executor**: point it at your tools, get the wiring graph and a runnable plan,
then hand execution to LangGraph / Dagster / a shell / your own runner. It wins
its niche (decentralized, evidence-cited capability discovery) and composes with,
rather than replaces, the engines that win theirs.

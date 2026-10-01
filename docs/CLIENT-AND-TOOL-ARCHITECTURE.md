# Flywheel client and tool architecture

Flywheel ships as a full native harness client with a bundled execution engine.
It owns the task loop, model routing, tool dispatch, permission checks and local
work records. Users can work in Flywheel itself without another harness client.
The engine also has a CLI and an API for supported integrations.

## Component responsibilities

| Component | Responsibility |
| - | - |
| Flywheel native client | The installed application: projects, chat, coding, model connections, approvals and results |
| Flywheel engine | Routing, task execution, tool grants, runtime lifecycle and local records |
| Rowan | The interaction and operator experience within the client, using the selected model |
| Articulate | Prose processing, host-edit instructions and preservation checks, callable as a tool and integrated through supported boundaries |
| Other tool lanes | Their own named capabilities and resource permissions |
| Client adapters and plugins | Access to selected tools or workflows from another supported client |

The suite is BYOM. The selected model supplies reasoning and generation;
tools supply capabilities and results. Flywheel's existing local model is the
sole model exception in the product architecture. Articulate, Rowan and tool
plugins introduce no model weights or publisher-operated inference service.
An execution runtime bundled with a tool is distinct from a language model.
Whether a particular installer carries model assets requires its own artifact
receipt; this document does not establish that packaging result.

## One execution architecture

The native client sends work to its packaged engine. The engine uses the chosen
model route and admits tool actions through permission checks. Results and
records return to the client. Rowan participates in this client experience;
Articulate and other lanes provide capabilities to the execution path.

An adapter for another client reuses a tool's supported interface and runtime.
It must not duplicate model routing, invent another permission authority or
require publisher-funded compute. A tool can retain its independent CLI or MCP
entrypoint while participating in the Flywheel application. Installation of a
workflow skill does not establish installation of the engine or desktop app.

## Existing implementation seams

- [GatewayProcess](../desktop/lib/services/gateway_process.dart) resolves the
  packaged engine next to the application and owns its launch lifecycle.
  Automatic startup requires that bundled engine; source development has a
  separate explicit fallback.
- The [view factory](../desktop/lib/shell/view_factory.dart) connects native
  chat, coding, model selection and other application views to the gateway.
- The [lane registry](../harness/lanes_registry.py) describes the integrated
  tool entrypoints, including Articulate's dependency-free MCP transport.
- The [CLI entrypoint](../harness/cli_entry.py) exposes the engine independently
  of the desktop surface.
- The [desktop release workflow](../.github/workflows/desktop-release.yml)
  assembles the native candidate. Plugin archives accompany that candidate.
- The [Evidence Task plugin](../plugins/flywheel-evidence-task/README.md)
  exports a bounded workflow to existing hosts. It is a skill package.

These pointers establish source architecture. A native debug build, a plugin
manifest or a passing unit test does not establish installed acceptance of
the whole product.

## Release requirements

The primary product artifact is the full client with its required engine and
execution dependencies. Compatible plugin and tool artifacts accompany the
same accepted release. Their manifests identify their actual scope, source and
version. A plugin archive must never be presented as the full client installer.

Local operation must not require a publisher account, a cloud deployment or an
external identity service. Optional network connections need explicit grants
and must not create publisher compute charges. Local state and credentials
remain under the user's control. Runtime checks enforce those boundaries.

Qualify the installed application and each claimed client connection with real
workflow checks. Match the integrated tool versions to the versions tested in
the client; separate repository tests do not establish composition. Preserve
the distinction between built, tested, installed, released and listed.

The present release work focuses on packaging, client interoperability,
permissions and usable Articulate/Rowan workflows. Reasoning-trace evaluation
remains part of Flywheel's broader purpose and is outside this work's scope.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/plexus/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/plexus/main/docs/art/hero-light.svg" alt="plexus: Discovers what tools emit and consume, then wires them together. Clusters of small nodes, named discover, match, wire and run, are wired to their neighbours and bundled through a bright core." width="100%">
</picture>

# plexus

Discovers what tools emit and consume, then wires them together.

```
python -m pip install plexus-mesh
```

[![version: 0.4.0](https://img.shields.io/badge/version-0.4.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://pypi.org/project/plexus-mesh/)
[![CI](https://github.com/HarperZ9/plexus/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/plexus/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-FSL--1.1--MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/plexus/blob/main/LICENSE)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-e6e1d6?style=flat-square&labelColor=1a1712)

**Capability discovery and auto-wiring for agent toolchains.** Point it at a set
of tools and it discovers what each one emits and consumes, then wires producer
to consumer into a runnable pipeline. Zero runtime dependencies.

MCP tells an agent *that tools exist*. plexus tells it *how their outputs plug
into each other's inputs*: the layer above a flat tool list.

GitHub-only release install for 0.4.0 on Bash/macOS/Linux:

```bash
set -euo pipefail
VERSION=0.4.0
BASE="https://github.com/HarperZ9/plexus/releases/download/v0.4.0"
WHEEL="plexus_mesh-${VERSION}-py3-none-any.whl"
SDIST="plexus_mesh-${VERSION}.tar.gz"
SUMS="SHA256SUMS.txt"
curl -fL -o "$WHEEL" "${BASE}/${WHEEL}"
curl -fL -o "$SDIST" "${BASE}/${SDIST}"
curl -fL -o "$SUMS" "${BASE}/${SUMS}"
python - "$WHEEL" "$SDIST" "$SUMS" <<'PY'
import hashlib
import re
import sys
from pathlib import Path

required = list(sys.argv[1:3])
sums = Path(sys.argv[3])
expected = {}
for line_number, raw_line in enumerate(sums.read_text(encoding="utf-8").splitlines(), 1):
    line = raw_line.strip()
    if not line:
        continue
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        raise SystemExit(f"malformed checksum line {line_number}")
    digest, name = parts[0].lower(), parts[1].lstrip("*")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SystemExit(f"invalid checksum for {name}")
    if Path(name).name != name:
        raise SystemExit(f"unexpected checksum path: {name}")
    if name not in required:
        raise SystemExit(f"unexpected checksum entry: {name}")
    if name in expected:
        raise SystemExit(f"duplicate checksum entry: {name}")
    expected[name] = digest
missing = [name for name in required if name not in expected]
if missing:
    raise SystemExit(f"missing checksum entry: {', '.join(missing)}")
for name in required:
    got = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    if got != expected[name]:
        raise SystemExit(f"{name}: expected {expected[name]}, got {got}")
PY
python -m pip install "$WHEEL"
```

GitHub-only release install for 0.4.0 on native PowerShell:

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Version = "0.4.0"
    $Base = "https://github.com/HarperZ9/plexus/releases/download/v0.4.0"
    $Wheel = "plexus_mesh-$Version-py3-none-any.whl"
    $Sdist = "plexus_mesh-$Version.tar.gz"
    $Sums = "SHA256SUMS.txt"
    $Files = @($Wheel, $Sdist, $Sums)
    foreach ($Name in $Files) {
        Invoke-WebRequest -Uri "$Base/$Name" -OutFile $Name
    }
    $Required = @($Wheel, $Sdist)
    $Expected = @{}
    $LineNumber = 0
    Get-Content -LiteralPath $Sums | ForEach-Object {
        $LineNumber += 1
        $Line = $_.Trim()
        if (-not $Line) { return }
        $Parts = $Line -split '\s+', 2
        if ($Parts.Count -ne 2) { throw "malformed checksum line $LineNumber" }
        $Digest = $Parts[0].ToLowerInvariant()
        $Name = $Parts[1].TrimStart("*")
        if ($Digest -notmatch '^[0-9a-f]{64}$') { throw "invalid checksum for $Name" }
        if ([IO.Path]::GetFileName($Name) -ne $Name) { throw "unexpected checksum path: $Name" }
        if ($Required -notcontains $Name) { throw "unexpected checksum entry: $Name" }
        if ($Expected.ContainsKey($Name)) { throw "duplicate checksum entry: $Name" }
        $Expected[$Name] = $Digest
    }
    foreach ($Name in $Required) {
        if (-not $Expected.ContainsKey($Name)) { throw "missing checksum entry: $Name" }
        $Got = (Get-FileHash -Algorithm SHA256 -Path $Name).Hash.ToLowerInvariant()
        if ($Got -ne $Expected[$Name]) {
            throw "${Name}: expected $($Expected[$Name]), got $Got"
        }
    }
    python -m pip install $Wheel
}
```

`plexus-mesh` 0.4.0 is published on PyPI; install it with `python -m pip install plexus-mesh`. The GitHub wheel recipes above download the 0.4.0 GitHub Release assets and check them against `SHA256SUMS.txt`. A source branch or
CI run is not a release; install from the GitHub `v0.4.0` assets only after the
wheel, sdist, and `SHA256SUMS.txt` are attached to that release.

```
$ plexus discover --builtin
$ plexus plan --goal crucible
$ plexus route --from gather --to crucible
$ plexus graph --format mermaid       # a diagram of the whole mesh
$ plexus run --goal crucible          # a runnable pipeline script
$ plexus mcp                          # stdio MCP server for agents to query live
```

An agent (Claude Code or any MCP client) can point at `plexus mcp` and call
`plexus_discover` / `plexus_plan` / `plexus_route` while it works, so the mesh is
consumable mid-task, not just from a human's terminal.

How it compares to MCP / LangGraph / Dagster / CrewAI: see [COMPARISON.md](COMPARISON.md).
plexus is the discovery layer that sits *above* an executor, not another executor.

<p align="center"><img src="docs/art/wiring-lane.svg" alt="Eight stages from manifest to verify, ending in still holds or drifted." width="100%"></p>

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/plexus.html)
walks through two small manifests wired into one edge, the unmet input and terminal output plexus names, a plan with its receipt, verify passing and then failing after a manifest changes, and the built-in ten-tool mesh. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install from PyPI. Python 3.11 or newer; discovery runs no tool.

   ```text
   $ python -m pip install plexus-mesh
   ```

2. **First run: is there a route?.** Ask whether one tool's output can reach another's input through the built-in manifests.

   ```text
   $ plexus route --from gather --to crucible --builtin
     "connected": true,
     "hops": 1,
   ```

3. **Discover your own tools.** Point plexus at a folder of manifests to see each tool's ports.

   ```text
   $ plexus discover --dir m
   producer    notes
   consumer    review
   capability  notes.summary/1
   self_loop   false
   via         src/notes/summary.py:build
   evidence    declared
   ```

4. **Plan and verify a pipeline.** Plan a pipeline toward a goal, then verify the plan against the manifests you have now.

   ```text
   $ plexus plan --dir m --goal review
   order    notes -> review
   sources  notes
   cyclic   []
   receipt  plexus.plan-receipt/1, method plexus-plan/1
     notes   53ab6c24d374afa4...
     review  0d50accb0759561e...
     plan_sha256  aeb01289ea823d89...
   ```

## The problem

You wire up a set of tools. Each one produces artifacts and accepts inputs, but
nothing knows how they connect, so you hand-wire `A | B | C` every time and
rediscover the plumbing on every new task. plexus makes the toolchain
self-describing: each tool ships a small manifest of what it emits and consumes,
and plexus computes the wiring graph: which tool's output is which tool's input.

## What you get

**Discover the mesh.** Producer-to-consumer edges by capability, shown here as
an excerpt:

```
$ plexus wiring --builtin
{
  "canon.capsule/v1":                  [["canon","canon"]],
  "canon.record/v1":                   [["canon","canon"]],
  "crucible.replay-pack/1":           [["mneme", "crucible"]],
  "crucible.replay-template/1":       [["crucible", "mneme"]],
  "crucible.thesis/1":                [["mneme", "crucible"]],
  "gather.digest/1":                  [["gather", "crucible"]],
  "gather.items/1":                   [["gather", "mneme"]],
  "index.verification/1":             [["index", "crucible"]],
  "project-telos.flagship-action/v1": [["crucible","index"],["forum","index"],["gather","index"]],
  "relay.rvc/v1":                     [["relay","relay"]],
  "relay.session-ledger/1":           [["relay","relay"]]
}
```

The Mneme/Crucible replay loop is bidirectional and schema-exact: Crucible emits
`crucible.replay-template/1` for Mneme to consume, and Mneme emits
`crucible.replay-pack/1` for Crucible to consume. The existing
`crucible.thesis/1` Mneme→Crucible route remains a separate declared edge,
satisfied by Mneme's native `mneme.crucible-export/2` export.

**Plan a pipeline.** "I want to feed `crucible`. What produces its inputs?"

```
$ plexus plan --goal crucible
  order:   forum -> gather -> crucible -> index -> learn -> mneme -> telos
  sources: forum, gather
  cyclic:  crucible, index, learn, mneme, telos  # feedback loops, reported not hidden
```

**Route between two tools.** "I have `gather` output and want a `crucible`
verdict. How do they connect?"

```
$ plexus route --from gather --to crucible
  [gather -> crucible via gather.digest/1]
```

**A plan you can re-verify.** Every `plan` and `route` carries a receipt that binds the
wiring to the exact manifests it came from: the content hash of every organ, plus a hash
over the derived plan. Save a plan, and later re-check it against the live mesh:

```
$ plexus plan --goal crucible --builtin > plan.json
$ plexus verify --plan plan.json --builtin     # exit 0 if it still holds, 1 if it drifted
```

`verify` re-derives the plan from the manifests (it never trusts the saved body), so a
tampered plan is caught, and a tool whose manifest changed since the plan makes the wiring
drift **visible** instead of letting it silently shift under you. Exit non-zero on drift,
so it works as a CI check over your toolchain's wiring.

Two things make that check worth running. `verify` rebuilds the receipt from the
plan it just re-derived, not from the one saved in the file, so editing the saved
body cannot make it agree with itself. And the receipt carries a method version
that has to match before anything else is compared, so a plan written by an older
plexus is reported as failing rather than silently re-interpreted under new rules.

Not sure which tool a request belongs to? `plexus pick "REQUEST"` returns a probability for each tool and abstains when none fits. Measured results are in [docs/PICK.md](docs/PICK.md).

## How a tool plugs in

A manifest is plain JSON. A tool ships one and it joins the mesh. Drop
`*.interop.json` files in a directory and `plexus discover --dir DIR` reads them:

```json
{
  "organ": "mytool",
  "invoke": {"cli": "mytool", "mcp_server": "mytool.mcp:serve", "python_import": "mytool"},
  "emits": [
    {"capability": "mytool.report/1", "title": "analysis report",
     "module": "src/mytool/report.py:build", "consumable_as": ["crucible.thesis/1"]}
  ],
  "consumes": [
    {"capability": "gather.digest/1", "title": "evidence intake",
     "module": "src/mytool/intake.py:load"}
  ]
}
```

An edge `A -> B` forms when `B` consumes a capability that `A` emits (directly,
or via `consumable_as`, the way a producer declares "my output is also
consumable as X"). Matching is by capability string, so an edge exists wherever
the tools DECLARE compatible capabilities. Declarative discovery does not run the tools, so the edge is a declared claim, not a probed result.

Plexus commits the built-in registry's exported JSON manifests under
[`manifests/`](manifests/). Discovery from these Plexus-side files produces the
same declared mesh as the built-in registry, as checked by a round-trip test.
Their presence here does not establish that each tool publishes its own manifest
or that a declared route has been exercised.

### Extended manifests (September 2026)

The registry now covers **ten organs**. Canon and Relay are the two visible
flagship roles for context and connectivity; Index, mneme, and Plexus keep their
component boundaries instead of being collapsed into a database or executor.

- **canon**: context and continuity flagship. It declares the shipped record
  envelope, continuity capsule, readiness probe, bootstrap witness, and read-only
  MCP surface. It does not declare universal context capture or shared preflight
  as shipped.
- **relay**: connectivity and execution flagship. It declares the endpoint
  ladder, MCP run request/result surfaces, hash-chained session ledgers,
  Relay-Verified-Correctness certificates, and remote MCP endpoint. It does not
  declare Canon capsules or Plexus route receipts as consumed until Relay ships
  that adapter.
- **mneme**: memory recall, provenance chain, and drift component. It remains a
  component under the context role, with its CLI/MCP compatibility intact.
- **index**: gatherer and source-context component. It still owns workspace
  scanning, context envelopes, freshness, and verification outputs; those are
  derived evidence, not authoritative memory.
- **learn**: tutor credential/mastery ledger entries, proof lessons,
  misconceptions. Consumes crucible theses for proof-lesson derivation.
- **telos**: room summary, golden workflow verification, workbench status.
  Consumes flagship-action envelopes for cross-tool reconciliation.
- **flywheel-infra**: 10 capabilities from the Flywheel infrastructure
  controls (egress, lesson, tool-call-receipt, TADR classification,
  governance envelope, credential scan, correlated event, isolation test,
  kill switch, run BOM). Consumes accountable-surface actuation outcomes,
  mneme drift reports, and learn misconceptions for lesson derivation.

### Probe mode

`probe_lane(name)` actually spawns a lane's MCP server and calls
`tools/list` + `status`, returning `{reachable, tools, error}`. Unlike the
declared manifest (which cites source files without running them), the probe
verifies the lane is live. `probe_all()` probes every registered lane.

```python
from plexus.registry import probe_all
results = probe_all(timeout=10)
for r in results:
    print(f"{r['name']:20} reachable={r['reachable']} tools={len(r['tools'])}")
```

## Declared, not probed

<p align="center"><img src="docs/art/edge-evidence.svg" alt="The six keys plexus discover returns for one wiring edge, one to a row, each with what settled it. Four are computed by discovery: the producing organ, the consuming organ, the capability that matched, and whether both ends are the same organ. One is copied out of a manifest without being read: via, the producer's own pointer at the code behind the port. One is a constant: evidence, always the word declared. The via row is accented, because it is the field that looks like a citation and is the one plexus never follows." width="100%"></p>

Every edge is tagged `evidence: "declared"` and cites the **module** its producer
names as the source (`file:function`). Declarative discovery does not import,
resolve, or run that pointer, so the citation is a self-reported claim to check,
not a verified receipt. The running tool re-checks none of the built-in manifests, so treat
every edge as declared until you follow the pointer yourself. Mneme's contract
was refreshed from public main on 2026-09-14, including
`mneme.crucible-export/2` and `mneme.local-origin-recheck/1`. Canon and Relay
were added from public origin-main source on 2026-09-16, and their manifests use
only repo-relative public paths. They intentionally leave Canon-to-Relay and
Relay-to-Plexus routes disconnected until a public shipped consumer exists.

plexus is also honest about what does **not** connect:

- `orphans().unmet_inputs`: capabilities something consumes that nothing in the
  set emits (an external or human input).
- `orphans().unconsumed_outputs`: artifacts nobody downstream consumes (terminal
  outputs).
- `plan(...).cyclic`: feedback loops, surfaced instead of forced into a false
  linear order.
- `discover().collisions`: organ ids declared by more than one manifest, named
  rather than silently resolved last-writer-wins.

<p align="center"><img src="docs/art/honesty-lane.svg" alt="Eight stages from a tool set to a report, ending in wired, colliding, or unmet." width="100%"></p>

An unmet input is a capability something consumes that nothing in the set emits,
and an unconsumed output is the mirror of it. Both fall out of the same
comparison, so neither is a special case someone remembered to write. The set is
also exactly what you handed it: plexus reads the manifests present and reasons
about nothing else, which is why an unmet input means only that no manifest here
produces it, not that no such tool exists.

## Receipt

`plexus discover` stamps a `receipt` on its output: the plexus version, a UTC
timestamp, and for every manifest read its `source` (`builtin:registry` or the
file path) plus a `sha256` over the manifest's canonical content. The hash binds
what was declared, so a stranger can recompute it from the same bytes and pin the
mesh to exactly the manifests that produced it.

## Install

```
python -m pip install plexus_mesh-0.4.0-py3-none-any.whl
```

Use the GitHub release asset and verify it against `SHA256SUMS.txt` first, or
install `plexus-mesh` from PyPI, which carries every release from 0.2.2 on. The installed package covers declared and synthetic mesh workflows; it
does not prove that real external lanes are live or that `probe_lane()` has been
run against owned services.

## Library

```python
from plexus import (builtin_manifests, discover, plan_to, route,
                    to_mermaid, pipeline_script)

mesh = discover(builtin_manifests())
mesh.edges                      # every producer -> consumer edge, each tagged declared
mesh.wiring()                   # capability -> [(producer, consumer)]
mesh.orphans()                  # unmet inputs / unconsumed outputs
plan_to(mesh, "crucible")       # the upstream pipeline (+ any cycles)
route(mesh, "gather", "crucible")   # the capability path between two tools
to_mermaid(mesh)                # a Mermaid diagram of the mesh
pipeline_script(mesh, "crucible")   # a runnable shell pipeline
```

## License

Plexus is fair-source: open to read, run, and build on, with commercial use reserved so the project can fund its own development. See [LICENSE](LICENSE).

## What this believes

This tool is one part of a family that holds a single belief steady across
every surface: knowledge open to anyone who can attain the means; acceptance
decided by external checks, never reputation; every result re-runnable;
honest nulls first-class; ownership earned by comprehension; learning woven
into the work. The full text lives in [CREDO.md](CREDO.md).
The long form of this belief: [The Unbundling](https://github.com/HarperZ9/flywheel/blob/main/docs/essays/2026-07-13-the-unbundling.md).

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).

## Local client packages

The additional [client package](client-plugin/README.md) includes portable plugin metadata and a Windows x64 MCPB/ZIP build. Version 0.3.0 first attached these packages to its GitHub release, and a published GitHub release for each later version carries packages built from that tag. Native packages carry their Python runtime. No publisher backend is required.

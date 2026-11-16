# Senses: one item, every tool that takes it

`plexus fanout ITEM` reads what kind of thing ITEM is, finds every tool whose
manifest accepts that kind, runs each one under a time and memory budget, and
writes one bundle with every answer. A tool that fails, times out, is refused by
the policy or cannot be reached on this machine is a row in the bundle with its
reason. Nothing is dropped.

```
plexus kinds picture.png                      # what kind of item is this?
plexus senses --kind image                    # which tools take a picture?
plexus fanout picture.png --config local.json # run them all; one bundle
plexus fanout picture.png --dry-run           # plan and check policy; run nothing
plexus fanout-verify plexus-fanout/picture.png-*/bundle.json
plexus pick "measure the symmetry of a drawing" --senses
plexus mcp          # read-only server: discover, wiring, plan, route, pick, kinds, senses
plexus mcp --run    # the same, plus plexus_fanout
```

## Input kinds

Thirty-five kinds, fixed in `src/plexus/kinds.py` (`KINDS`). `detect` reads them
from the item itself and never opens a connection:

| Read from | Kinds |
|---|---|
| file signature (first 64 KiB) | image, pdf, archive, audio, video, model3d, table (SQLite) |
| extension, confirmed by the bytes or for text formats | prose, code, table, html, vector, model3d |
| text sniffing | feed (RSS, Atom), html, vector (SVG), table and series (delimited numbers), spectrum (a numeric column named for nm or Hz), claim, lens, circuit, post (JSON) |
| a file beside the item with the same name and `.md` or `.json` | post |
| a directory | folder; repo when it holds `.git` |
| URL shape | web; post (social hosts); paper (arXiv, DOI and preprint hosts); feed; and the kind of the URL's extension |
| short literal | colour (hex, `rgb()` and friends), paper (arXiv id, DOI), formula (registry id), seed (integer), claim (JSON), prose (three words or more) |

An extension alone never makes a binary kind: a `.png` full of text is not a
picture. Nine kinds describe content rather than form and no byte pattern shows
them: voice, music, field, geometry, material, symbols, memory, law, screen
(`CALLER_ONLY`). A caller adds them with `--kind`. When nothing fits, the answer
has `unknown: true` and a reason: `empty item`, `no such path`, `no kind fits`,
or `no kind beyond file fits` for bytes no rule recognises.

## The catalogue and its manifests

`src/plexus/sense_data/SENSES.tsv` lists the tools, one row each, with input
kinds, what each returns, the exact call, whether it was verified by running it,
and its cost. Machine columns add the run block (`cli` argv or an MCP server and
tool, with `{item}`, `{text}`, `{out}`, `{python}` and `{node}` placeholders), the
item forms it takes (path, URL or literal), extensions it is limited to, network
use, and its time and memory budget.

`python scripts/gen_senses.py` writes one manifest per row an agent can call
today to `src/plexus/sense_data/manifests/`. `--check` (and the test
`test_committed_manifests_are_in_step_with_the_table`) fails on any manifest that
differs from the table, any missing one and any stray one, so the two cannot
drift. A kind outside the vocabulary stops generation.

Machine-specific settings never enter the repository. A local JSON config names
where the source trees live and how to start MCP servers:

```json
{"roots": {"superframe": "PATH", "portfolio-site": "PATH"},
 "python": "PATH-TO-PYTHON", "node": "node",
 "mcp_servers": {"name": {"command": "EXE", "args": []}},
 "mcp_config": "PATH-TO-A-CLAUDE-STYLE-CONFIG"}
```

`mcp_config` is read for its `mcpServers`; nothing writes to it. A tool whose
root or server is not configured is reported `unavailable`.

## Policy

`src/plexus/sense_data/policy.json` is the boundary, read before any tool starts.
`plexus.policy.refusals` turns it into reasons; a tool with any reason is not
started and the reasons are written to the bundle.

| Rule | Mechanism |
|---|---|
| Network is off. A tool may use it only when its manifest declares `network: true` and the call grants that tool (`--grant-network ID`). | refusal before launch |
| Kinds: only listed kinds may be routed; `screen` needs `--grant-kind screen`. | refusal before launch |
| Tools on the refuse list (hosted multi-model runs, an uncalibrated router) never run. | refusal before launch |
| A budget above the ceiling (300 s, 4096 MB) is refused, not clipped. | refusal before launch |
| A tool may write only under its own output folder. | refusal of any declared write elsewhere |
| A call may name only the item, the configured source root and its output folder as paths. | refusal of any other absolute path in argv, environment or MCP arguments |
| Time | Windows: Job Object terminated at the limit, child processes included. POSIX: the process session is killed. |
| Memory | Windows: Job Object memory limit for the whole job. Linux: `RLIMIT_AS`. macOS records the limit and the peak but does not enforce it. |
| Output | stdout over 64 MB is cut and the cut is recorded. |

These checks act on what a tool declares and on the command line plexus builds.
They are not an operating-system sandbox: a tool that opens a socket, or a path
it never names on its command line, is not stopped by them.

The test `test_planted_manifest_that_exceeds_the_policy_is_refused_and_never_runs`
plants five manifests (time over the ceiling, memory over the ceiling, network
without a grant, a write outside its folder, a path outside the item) whose
command would create a file; all five come back `refused` and the file is never
created. Other tests stop a tool at its time limit and a 600 MB allocation under
a 200 MB limit.

## The bundle

`bundle.json` holds the item, its sha256, its kinds with the evidence for each,
the policy's sha256 and one row per matched tool: `status` (`ok`, `empty`,
`failed`, `timeout`, `refused`, `unavailable`, `not runnable`, `not applicable`,
`skipped`), the reason or error, seconds, peak memory, and the path and sha256 of
its output. The receipt binds the manifest hash of every tool, every output hash
and the policy hash; `plexus fanout-verify` recomputes them.

## pick and the senses

`plexus pick` ranks the flagship tools by BM25 and abstains under 0.23, the
threshold calibrated on a labelled set of 51 held-out requests (`docs/PICK.md`).
`--senses` (MCP: `senses: true`) adds the sense manifests to the ranking. That
mix is not calibrated: on the same labelled set, top-1 accuracy falls from 0.57
(Wilson 0.43 to 0.70) to 0.35 (0.24 to 0.49), partly because a request labelled
`gather` now meets `gather.pdf` and `gather.decompose` as separate entries. Route
an item by its kinds; use pick for a request in words.

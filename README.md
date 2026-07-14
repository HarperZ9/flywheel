# Flywheel Desktop

The native desktop surface for [Flywheel](https://github.com/HarperZ9/flywheel):
one window over the whole platform. Route any model, watch the verified loop,
read the receipts. No browser, no terminal.

## What you get

- **Lanes** — the flagship tool family (gather, crucible, index, forum, learn,
  telos, local-model) with live health. Probing spawns each tool's own MCP
  server and asks it directly; the verdict shown is the tool's answer.
- **World** — the projected, root-hashed state. Recomputed on every read:
  tamper any cataloged receipt and the hash moves.
- **Receipts** — the ledger of re-checkable artifacts: the in-repo catalog,
  re-hashed on every read, and the proof envelopes written when verified work
  is accepted. No receipt, no accept.
- **Code** — an IDE lane: open any folder, edit with highlighting and Ctrl+S,
  and put the agent to work on the workspace itself. Large and binary files
  open read-only and say so.
- **Companion** — ask once, the seat answers from the cheapest honest source.
  Verified and cached answers carry a verified chip; agreement without proof
  is labeled consensus; hard prompts escalate with the failed local attempt on
  record. The chip never lies.
- **Agent** — the gated, witnessed tool loop over any endpoint. Older model
  generations inherit the same loop, gates, ledger, and integrity verdict as
  the newest; write and exec stay off until you grant them.
- **Workflows** — staged runs (plan, apply, verify; draft, critique) shaped by
  profile manifests (code, design, work, cowork), over any endpoint, each run
  folded into one chained receipt. Verification without an exec grant reports
  UNVERIFIABLE instead of pretending.
- **Studio** — creation with provenance: seeded generative plates (the seed is
  recorded on the mark), the loop schematic drawn from live state, and honest
  nulls for what is not shipped yet.
- **Projects** — register your directories once; Code, Lint, Plan, and the
  agent pick a project instead of taking a typed path.
- **Plan** — spec first, receipt after: a goal becomes a criterion-bearing
  plan whose validation gates are marked by what an external oracle can run,
  then hands off to a staged, receipted workflow run.
- **Lint** — a native linter whose findings are content-addressed receipts;
  a finding can hand off to the agent to fix.
- **Graph** — the cross-surface knowledge graph, interactive: shape encodes
  kind, size encodes engine-computed priority, and a budget plus query turn
  the graph into a context plan whose exclusions stay counted.
- **Feeds** — fresh signal across science, programming, art, design,
  marketing, and accountability, fetched with provenance; a dead feed is a
  named error, never a silent gap.
- **Science** — evidence, spec, judgment, one chain: gathered sources with
  provenance, the question priced as a research spec, and witnessed claim
  verdicts where an unmeasured claim stays UNVERIFIABLE.
- **Uplift** — the paired-arm bench, read-only: bare vs the verified loop
  with intervals; an interval containing zero renders as the honest null it
  is, and the wrapper's latency cost stays visible.
- **Memory** — durable, content-addressed memory: notes and folded spans with
  verbatim recall, the span hash as provenance.
- **Endpoints** — the universal router roster. Local tiers are probed live;
  hosted providers show credential presence only (the env var name, never a
  value); the scoreboard shows observed routing outcomes, not promises. The
  read-only training card reports the local run as it is.

## Run it

Install the engine and start it once:

```
pip install flywheel
flywheel up
```

Then run the app:

```
flutter run -d windows --release
```

If the engine is offline the app says so and can start it for you.

## Design

Hanken Grotesk and Conso ship as the default pair, and the surface is yours:
text family, mono family, and UI scale are user settings (the tune control
at the rail's foot), applied live and persisted. Panels resize by dragging
their hairline dividers; layouts adapt to narrow windows. One rule is not on
the menu, because it is what keeps the surface readable: color only ever
means a verdict. Verified green, drift iris, unverifiable gray. Ceramic
light and near-black dark themes, both AA; cards are ground tints with a
hairline border; no glass, no decorative color.

## What this believes

One belief across the whole family, kept as a content-addressed artifact
([CREDO.md](CREDO.md), served live by the engine at `GET /api/credo`):
knowledge open to anyone who can attain the means, and we build to lower the
means; acceptance decided by external checks, never reputation; honest nulls
first-class; ownership earned by comprehension; learning woven into the work.

## Build and test

```
flutter analyze
flutter test
flutter build windows --release
```

## Honest boundaries

The app displays what the engine can prove and labels what it cannot. Model
answers that fail verification are shown as escalations, not dressed up as
results. Credentials are never collected, stored, or displayed by this app.

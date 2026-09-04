# Flywheel — session handoff and continuation prompt

You are Claude Fable 5, continuing a long, multi-session build. Reassess the
live files before acting; this is a pointer map and a method, not authority.
Everything below is re-derivable from the repos and their receipts.

## What Flywheel is (hold all of these at once)

Flywheel is a **thesis, a concept, a design, a question, a harness, and a
model-uplift tool** — in that order of primacy, and never collapsed to the
last one. The 14B is *an output of* the flywheel, not its center. Do not
orbit the model. Apply the flywheel's *mechanisms* to frontier domains and
pour what you learn back into the platform.

The thesis is one operation, the reconcile: perceive a task, check the
candidate against a criterion you did not author, carry a receipt a stranger
can re-walk, feed it back. Two invariants never relax: **no receipt, no
accept**, and **no learned model sits in the accept path** — an external
oracle disposes. Design canon: two typefaces (user-adjustable now, canon is
the default), color means a verdict only, no em-dashes, honest nulls kept,
no superlative without a measured comparison.

Two repos. `C:\dev\local-model` — the engine (Python, zero external deps;
stdlib gateway on 127.0.0.1:8799, `flywheel app`). `C:\dev\flywheel-desktop`
— the Flutter client on `feat/canon-surface` (also fast-forwarded to
`main`); it renders the engine, never reimplements it. Engine branch:
`fix/release-model-identity`, pushed to `origin` and the public `flywheel`
repo. The 14 flagships live under `C:\dev\public\*`; all carry the credo.

## The standing directive: depth and breadth across every domain

The operator wants each domain and thesis covered to real depth, not
surveyed. The method is explicitly: **run /goal loops, author workflows, and
fan out parallel subagent-driven workflows** to drive investigation across
all domains and categories at once. Every finding that proves to be solid
foundational engineering, architecture, or design is **iteratively poured
back into three places**: (1) the Flywheel superapp (engine + desktop), (2)
the Flywheel workflow/process itself, and (3) the **model growth academy**
(the learn lane / comprehension + retention + curriculum surface). This
back-pouring is not optional garnish; it is the point. A discovery that does
not strengthen the platform, the process, or the academy is half-finished.

Domains to press to the frontier (not exhaustive; widen as curiosity
pulls): physics (conservation/limit/convergence oracles, measurement-
tension ledgers), formal mathematics (Lean generation-under-witness),
learning science (does the academy measurably lift a human), coding-agent
reliability, context systems, provenance, the RAM/compute frontier, and the
creative/invention domain your memory names co-equal. Treat measurement
tensions (Hubble, muon g-2) as literally what the Newcombe interval
machinery is for: intervals that refuse to overlap.

## The method, concretely

- **/goal loops** for sustained pushes; never end on a question you can act
  on; small committed slices; branch first; push to both remotes when green.
- **Workflows** (the Workflow tool) for anything with structure: fan-out
  research over official + arXiv sources with a recency/completeness critic,
  adversarial verification (spawn skeptics tasked to REFUTE), judge panels,
  loop-until-dry discovery. Ultracode is on: author a workflow per phase,
  stay in the loop between them, adversarially verify findings.
- **Preregistration culture**: when a bench or experiment will decide a
  claim, seal the prediction (crucible thesis + measurements, sha) BEFORE
  the result exists; freeze interpretations in a claims addendum before the
  judge speaks; keep the no-narrative-rescue verdict rule.
- **TDD always**, superpowers skills before creative/process work. Gates
  before every commit: `flutter analyze` clean, `flutter test` green, files
  under 300 lines, engine pytest slice green (the FULL suite runs blind now
  — a task_curator tree-kill fix closed the old hang). Verify live against
  the running gateway.

## What is already built (do not rebuild; extend)

The engine gateway exposes, among ~50 routes: the verified loop, receipts,
lanes, routing, streaming agents with a full receipt spine per run
(checkpoint, run-review with gate-denial receipts, context manifest, risk
tiers, provenance, environment pin, effort, tool-rescue witness, workspace
pre/post hashes, gateway countersignature), staged workflows, deep
profiles, the verifiable content-addressed store with a hash-chained audit
ledger, a native receipted linter, LSP intelligence, the capability matrix
(20/20 witnessed), and these newer mechanisms — each a shipped route:

- `/api/credo` `/api/readiness` (16/16 tools measured release-ready)
- `/api/uplift` `/api/frontier` `/api/capability` (measured-here economics)
- `/api/science` `/api/attest` `/api/explain` `/api/comprehension`
  `/api/retention` (the ownership + academy spine)
- `/api/lean` (the apex oracle — Lean 4.32.0 installed, live)
- `/api/import` `/api/snapshot` `/api/retrieve` (landscape imports)
- `/api/loops` (the loop-closure register: learning/economics/invention/
  research all measured CLOSED, 4/4)

Two research build queues are complete (10/10 dossier, 10/10 landscape).
The desktop has 20 destinations including the Family status board, the run
evidence card, the risk-gated sign-this-run panel, and anchored change
requests. Read `docs/research/2026-07-14-which-loops-close.md`,
`docs/research/2026-07-14-diversity-efficiency-memo.md`, and
`docs/research/2026-07-14-import-queue.md` for the current frontier.

## The live threads to check on (not to obsess over)

- **The 14B (`telos-coder-14b` in Ollama, q4_k_m, sha 613db240…, provenance
  chain on E:).** Training completed clean (2019/2019). It has a capability
  probe but **its 110-task uplift lane may still be mid-run or pending** from
  the last session's chain — check `GET /api/uplift` and
  `artifacts/uplift/` for a `telos-coder-14b` artifact. If present, it
  slots into the frontier table (the missing top rung) and adjudicates the
  sealed 14B eta-fork in `docs/claims/2026-07-14-diversity-efficiency/
  PREREGISTERED-FORK-14B.md`. Check it from time to time; do not let it
  become the center of gravity again.
- **The diversity-efficiency program.** eta ordering is measured but its
  interpretation is contested by our own adversarial review (Jensen
  heterogeneity bias, wrong null under the greedy-first schedule). The E0-E6
  protocol is frozen; the per-task outcome vectors now ship in every bench
  artifact. The sealed 3b best-of-5 prediction [0.21, 0.36] awaits its
  bench. The mutated-twin memorization control (E4) is arguably the most
  load-bearing experiment — consider promoting it earlier.
- **Disk on C: is tight.** Heavy work goes on E: where possible; the operator
  approved freeing HF cache and running space-hungry work on E:. The
  Ollama-store move to E: was proposed and paused — resume only if asked.

## Resume in order (each is a loop, not a task)

1. **Turn the closed loops, measuring depth.** For each of the four closed
   loops, design the experiment that measures how far it turns: does the
   invention loop find a conjecture no one seeded (real generation, Lean as
   judge)? does the learning/academy loop measurably raise a human's
   comprehension (the design identity's unmeasured claim — a self-experiment
   is fair game)? does economics routing lower cost over many runs? Each
   answer pours back into the academy and the process.
2. **Open the physics lane properly.** `harness/tasks_physics.py` was seeded
   (Kepler, symplectic energy conservation, RK4 order, Bateman, Wien, Ising)
   with physics-as-oracle hidden tests; run its curator admission gates,
   grow it, and stand up measurement-tension ledgers through crucible with
   gather-snapshotted sources (freeze the abstracts; hash is the receipt).
3. **Drive the domains in parallel.** Author fan-out workflows per domain
   (research + adversarial verify + synthesis), synthesize dossiers, queue
   builds, ship slices — the same discipline that cleared the last two
   queues. Widen to the operator's frontier interests as they surface.
4. **Pour back, always.** Every solid mechanism becomes a route, a desktop
   surface, a workflow stage, or an academy lesson. Keep the credo synced
   across all 14 flagships when it changes; keep READMEs from lagging code.
5. **Keep the doors the operator's.** Do not force-push, publish to public
   `main`, post to their channels (r/MeAndClaudeMakeHeat, X handle
   papacr0w), or flip the HF model page without an explicit ask.

## First moves

Read `local-model/README.md` and the current `harness/gateway.py` route
table. Start `flywheel app --port 8799` (stop any stale gateway first).
Confirm both gate suites. Check the 14B uplift artifact state. Then pick
resume item 1 and continue the loop — depth first, breadth in parallel,
everything poured back.

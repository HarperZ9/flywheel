# The Verified Data Flywheel

### A systems-efficiency answer to "A Stargate for Data"

> Response to Will Depue (OpenAI), *A Stargate for Data* (2026-07-06), and
> Andrej (@0xdrej) confirming it as an active build. This is not a rebuttal —
> the data-limited thesis is correct. It is the counter-move a lab **without**
> $100B/year for collection makes: not more data, but more value per datum.

## 1. The thesis, stated fairly

Depue's argument, which we accept: AI has crossed from the compute-limited
regime into the **data-limited** one. The public internet was a one-time
civilizational subsidy (~300T useful human tokens), it is nearly spent, RL's
reprieve (gradable math/code) is drying up too, and so the binding constraint on
automating the economy is now **data coverage** — the "dark matter" of tacit
knowledge and undocumented process sitting in people's heads and private stores.
His prescription is a civilizational-scale collection effort: >$100B/year,
licensing, expert labelers, a "Stargate for Data."

He names, and sets aside, the alternative: *data efficiency* — "synthetic data,
data-efficient architectures, other exotic algorithms" — on the grounds that
fundamental progress there is slow and unpredictable, while brute collection
"just works today."

**That set-aside is the opening.** A brute-force megaproject is the right move
for whoever can fund it. For everyone else, the leverage is exactly the axis he
tables: make each collected datum worth more, and manufacture the gradable data
the collection can't reach. That is a systems problem, and it is the one this
whole codebase was already built to solve.

## 2. Where systems efficiency beats spend (each grounded in a shipped module)

The Stargate treats data as a **reservoir** being depleted. We treat it as a
**flow** — and the fluid-dynamics work here is the model of that flow, not a
metaphor.

**(a) Provenance is the quality moat Depue names but does not solve.** He notes
data quality "can vary massively" and is a real differentiator, then proposes to
scale collection anyway. Our intake (`gather`) attaches a re-checkable receipt to
every datum — source, method, content hash — so a corpus is not a pile of tokens
of unknown origin but a set of facts a third party can re-derive. At equal
volume, verified data trains a more trustworthy model and, more importantly,
*localizes* the bad datum instead of laundering it into weights. Quality control
stops being manual review and becomes a property of the pipeline
(`dataset/receipt.py`: a corpus→shards→checkpoint chain that flags CORPUS_DRIFT).

**(b) Transpile-conservation: collect the criterion, not the bytes.** The
operator's own principle — a lossy transform conserves the task-relevant
*criterion*, not the bits — is a data-efficiency thesis stated precisely
(`harness/transpile.py`, validated in `perception_probe.py`). You do not need the
300T tokens; you need the criterion-invariant they carry. This reframes "we are
running out of data" as "we are keeping the wrong invariant." The turbulence
result makes it exact: above the critical parameter you *cannot* conserve the
trajectory (the raw tokens), only the statistical invariant (the criterion) —
`harness/turbulence.py`. In a data-limited world the disciplined move is to store
the distribution, not the sample.

**(c) The harness manufactures the gradable data RL is running out of.** Depue's
sharpest near-term point: chain-of-thought RL needs gradable tasks, and we are
"quickly running dry of hard tasks." The verified-inference loop here produces
exactly that — an oracle-backed (task, candidate, verdict) triple where the
verdict is re-checkable (`harness/loop.py`, `grounding.py`). Every accepted
solution is a new gradable RL datum *carrying its own grader*. The
`task_curator` already gates a hard-set to soundness (no vacuous tests, no
solution leak); point it at generation and it is a data factory whose output is
verifiable by construction. This is synthetic data with the property synthetic
data usually lacks: a witness.

**(d) The flywheel recirculates verified inference — with an honest ceiling.**
The `flywheel` / `evolutionary_flywheel` / `proof_cache` line is the recirculation
pump: verified outputs re-enter as verified inputs, and a proof-addressed cache
serves a result only when it re-verifies (no learned authority in the accept
path). The `valve_flywheel` + `backflow` valve makes it a **ratchet**: a new
datum is admitted only if it *exceeds* the banked frontier (a positive but
regressive datum is backpressure, blocked), so the corpus quality never
runs backward. This is the fluid-dynamics core: a pump with a check valve.

**(e) accountable-surface captures the dark matter in situ.** The undocumented
process "in someone's head" becomes data when you record the work being done,
with provenance, at the moment it happens — which is exactly what the gated
workstation actuator is for. Capture-in-place beats after-the-fact labeling on
both cost and fidelity, and it arrives receipted.

## 3. The honest ceiling — stated first, not buried

The flywheel does **not** repeal Depue's thesis, and pretending it does would be
the exact dishonesty this project exists to refuse. Our own ablation proved it:
the amortization ceiling is `1/(1-r)`, bounded by the reuse fraction `r`, with
**no compounding on genuinely novel work** (`harness/asymmetry.py`; the M7
capability lift did not reproduce and is quarantined as UNEARNED). Recirculation
amortizes the data you have; it does not conjure the data you lack. On truly
new coverage — a domain the corpus has never seen — the flywheel gives you
nothing, and only collection (Depue's Stargate) or a real data-efficient
architecture helps. So this is not "data efficiency defeats collection." It is:
**collection sets the coverage; systems efficiency sets how much of the
economy's value you extract per unit collected, and manufactures the gradable
slice collection can't reach.** The two are complements. The lab that pairs a
serious collection effort with this flywheel beats the lab that does either
alone.

## 4. What we build (on organs that already exist)

The proposal is not a new megaproject; it is wiring five shipped organs into one
loop and measuring it:

1. **Verified-intake corpus** — `gather` → `dataset/receipt.py`: every training
   datum carries a re-derivable source receipt; the corpus→checkpoint chain is
   drift-checkable. (Built; the checkpoint-2020 receipt exists.)
2. **Criterion extraction** — `transpile` + `perception_probe`: store the
   criterion-invariant, measure conservation. (Built; needs the data-efficiency
   benchmark: tokens-to-criterion ratio vs raw retention.)
3. **Gradable-data factory** — `loop` + `grounding` + `task_curator` in
   generation mode: manufacture (task, solution, witness) RL triples, gated for
   soundness. (Curator built; the generation-mode wire is the next increment.)
4. **Recirculation ratchet** — `flywheel` + `valve_flywheel`/`backflow` +
   `proof_cache`: recirculate verified outputs, admit only frontier-advancing
   data, serve only re-verifying results. (Built; needs the corpus-facing driver.)
5. **The ceiling meter** — `asymmetry`: report the reuse fraction `r` and the
   amortization bound honestly on every run, so no unearned "infinite data"
   claim can survive. (Built; already refused the M7 overclaim.)

The measurable headline this earns — and the only one we will publish — is a
**data-efficiency number with a receipt**: criterion conserved per token
retained, and verified RL triples manufactured per oracle call, each
re-derivable, against the honest amortization ceiling. Not "we made the next
internet." "We extract N× more verified, gradable value per collected token,
and here is the packet that proves it."

## 5. One line

The Stargate for Data scales the *reservoir*. The systems-efficiency move is to
engineer the *flow*: verify every datum, conserve the criterion not the bytes,
manufacture the gradable slice, recirculate through a one-way valve, and meter
the ceiling honestly. We cannot outspend the collection. We can make the
collection worth more — provably.

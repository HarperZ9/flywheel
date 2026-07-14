# The academy pipeline: curriculum derived from code, under witness

## The borrowed shape, credited

Zachary Huang's PocketFlow work (the 100-line framework, and the
Tutorial-Codebase-Knowledge pipeline, 12k+ stars, MIT) demonstrated a
teaching pipeline this platform now applies with attribution: crawl a
codebase, identify its core abstractions, order them into a narrative
arc from foundations to composition, and teach one abstraction per
chapter for a reader who has never seen the code. The insight worth
adopting is structural, not stylistic: the codebase itself already
contains its own curriculum, and the teaching order is the dependency
order of its abstractions.

Provenance note: the referenced video ("My plan for this Channel",
Zachary Huang) resisted transcript retrieval; this application grounds
in the published, documented form of the technique (the pipeline
repository and framework) rather than in unverifiable recall of the
video's contents.

## The difference that makes it ours

His pipeline narrates a codebase with a model. This academy binds a
curriculum to receipts:

- **The teach-text IS the live module docstring**, pinned by hash.
  Documentation rot breaks a lesson visibly instead of silently, and a
  source that cannot be imported yields an absent lesson, never a
  fabricated one.
- **Every lesson names an executable check** against the running
  gateway. The learner does not take the lesson's word; they run the
  mechanism and watch it answer.
- **Completion is a receipt, not a scroll event.** The teach-back goes
  through the explanation gate (a comprehension receipt banks in the
  verifiable store), and retention schedules the unaided retest. Held
  is what survives the retest, not what was once shown. The
  learning-academy dossier's central finding applies: assisted
  practice and unassisted outcomes are different measurements, and
  only the second one is competence.

Live at `GET /api/academy`: eight lessons today (store, envelope,
oracle, admission, loops, forge, tension, instruments), a valid
prerequisite arc, 8/8 present.

## The pipeline, staged

1. **Now (shipped):** the curated arc over this repository's core
   abstractions, derived live, receipt-bound.
2. **Next:** generalize the deriver over the import lane
   (`/api/import` already ingests external setups): point the pipeline
   at any repository and emit a receipted curriculum for it, with the
   same absent-not-fabricated rule for undocumented modules. This is
   where the surface converges with the codebase-to-tutorial project,
   and the two compose rather than compete: a narrated tutorial can be
   the teach-text; the receipts and retests stay ours.
3. **Then:** the educational platform proper. The desktop client
   renders the curriculum as a destination; per-learner state is the
   comprehension ledger plus the retention queue, which already exist
   as routes. The unmeasured claim stays unmeasured until someone runs
   it: whether this loop measurably lifts a human is the academy's
   sealed question, and a self-experiment protocol should be sealed
   before any such claim is made.

## Honest boundaries

- Eight lessons is a seed, not a curriculum. Growth follows the same
  admission discipline as everything else: a lesson whose source rots
  or whose check dies reads absent.
- Docstring-as-teach-text teaches the mechanism's intent, not usage
  walkthroughs; worked examples remain future work on the arc.
- Nothing here claims pedagogy superiority; the claim is narrower and
  checkable: every statement a lesson makes is pinned to a source a
  learner can open and a check a learner can run.

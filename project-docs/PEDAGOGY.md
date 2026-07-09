# How we teach, and how that shapes what we build

Date: 2026-07-09

This is a working guide, distilled from four educators the operator asked us to
learn from, and from their peers: Numberphile and the math communicators around
it, Anton Petrov and the wonder-forward science channels, Alisa Esage and the
adversarial-rigor school of security research, and Zachary Huang (ZacharyLLM)
and the local-model teaching community. The point is not to imitate them. It is
to let the best of how they teach change how we write and how we verify.

Two rivers run through this, and they meet. One is warmth: lead with the
question, honor the reader, say plainly what we do not know. The other is rigor:
trust is earned by trying to break a thing, not by asserting it. A good tool,
and a good explanation, needs both.

## The voice we want

These are drawn from how the math and science communicators actually work.
Sources are in the research notes; the confidence varies and is marked there.

1. Lead with the question, not the definition. Open a section with what is
   genuinely at stake or curious, the way Numberphile opens on a mystery rather
   than a formula. The definition can come once the reader wants it.
2. Show the concrete thing before the abstraction. A real receipt, a real log
   line, a real diff, before the general principle it illustrates. This is
   3Blue1Brown's visuals-before-formalism and Numberphile's kraft paper: the
   object first, the theory second.
3. Let the reader rediscover. Frame a walkthrough so the reader reconstructs
   why a choice works instead of being told to accept it. Grant Sanderson's
   point is that the ideas we own are the ones we had a hand in finding.
4. Name the wrong intuition before correcting it. If a term is commonly
   misread, say the misreading out loud first, then correct it. Derek Muller's
   doctoral research found this measurably beats clean exposition that never
   mentions the confusion. "Verified" is our first target: it does not mean
   "provably correct output," and we should say so before we say what it means.
5. A little friction is good. We do not have to pre-chew every hard idea into
   mush. A reader who works through real difficulty keeps more than one handed a
   frictionless gloss.
6. Warmth is a fixed habit, not a mood. Anton Petrov opens every video with
   "hello wonderful person." We will not copy the phrase, but we will keep the
   habit: a small, genuine welcome that tells a newcomer they belong here
   regardless of what they already know.
7. Say "we do not know yet" plainly when it is true. Uncertainty stated
   outright is more credible than confidence stretched past the evidence. This
   is the thread connecting Kurzgesagt's disclosed sourcing, Sabine
   Hossenfelder's stated no-hype ethos, and our own retired capability claim.
8. Show your work, not just your conclusion. Kurzgesagt publishes a per-video
   source sheet; Mathologer's friendly videos sit on a hidden review layer. Our
   equivalent already exists: the receipt. Make the reasoning visible, not just
   the verdict.
9. The on-ramp is gentle; the depth has no ceiling. Make the entry easy, then
   let the content go as deep as the truth requires. PBS Space Time's premise is
   that the universe is fundamentally gettable. So is a verification harness.
10. Let the system think out loud. Numberphile works because you watch a
    mathematician think. Our receipts and traces should expose decision points,
    not only pass or fail.
11. Humor and informality carry content; they never replace correctness. Matt
    Parker is a trained teacher first and a comedian second.
12. When a claim is contested, say so instead of picking one voice and calling
    it consensus. Represent the real disagreement rather than sanding it off.

## The discipline we want

These are drawn from the adversarial-rigor and local-model practitioners. They
are the same values the harness already holds, said in a sharper way.

1. Trust is earned by attempted falsification, not asserted by authority. An
   oracle that has never been attacked is unproven, not trustworthy. This is
   Alisa Esage's break-it-to-know-it and AFL's let-the-tool-find-what-a-human-
   cannot, and it is our own "the verifier must be able to fail."
2. Reconstruct from first principles instead of matching a pattern. Gynvael
   Coldwind teaches reverse engineering by writing a program, compiling it, and
   reversing your own binary back. Understand the generating mechanism, not the
   surface.
3. Real verification is slow, and budget pressure is not a reason to skip it.
   Do not accept a fast unverified answer just because it arrived on time.
4. Compose independent signals per claim. Static, dynamic, and behavioral
   analysis catch what any one misses; coverage feedback beats blind mutation.
   One pass signal is not enough for an accept.
5. Automated exhaustive search beats manual guessing. Coverage-guided fuzzing
   reaches states no human would think to test. Verifier-guided search over
   hand-written cases is the same idea.
6. Calibration data and evaluation data must never overlap. The Unsloth
   quantization writeup documents this exact self-deception: tune on Wikipedia,
   test on Wikipedia, and the numbers lie. Keep them disjoint, always.
7. A vendor's claim, or the model's claim about itself, is a lead, not
   evidence. Re-derive before accepting. Our model-card handling already treats
   upstream claims this way.
8. Reproducibility is the acceptance bar. A crash that will not reliably
   reproduce does not count; a proof envelope a third party cannot re-run to the
   same verdict does not count either.
9. Progressive difficulty exposes capability boundaries that aggregate scores
   hide. A graded ladder of tasks, not a flat pool, so a regression shows up at
   a specific rung. This is exactly why the hard-set lane is tiered.
10. Teach the mechanism, not the button. Strip the framework down until the
    underlying loop is visible. Zachary Huang's compression is "LLM agents are
    just loops with branches." Our docs should expose why a bound holds so an
    operator can extend the oracle registry, not just call it.

## Where this lands in the work

Concrete, and tied to real components. Some of these are done, some are the next
increments.

- Misconception-first onboarding in the walkthrough. Before defining "verified
  inference," state the wrong intuition a newcomer brings and correct it. (Voice
  4, Muller.)
- Wonder-forward model cards. Lead with what the model can newly do that is
  genuinely interesting, then the honest caveats and numbers, not the reverse.
  (Voice 1 and 7.)
- Honest-uncertainty labels on every benchmark number: reproduced, reproduced
  once, or not yet reproduced. This is already how the confidence-interval work
  reads the hard-set result, and how the retired +10% claim is handled. (Voice
  7, Discipline 6 and 7.)
- Adversarially test the oracle itself before trusting it to gate accepts.
  Known-bad candidates in the adversarial and failure corpora that a correct
  oracle must reject. This tests the checker, not only the model. (Discipline 1
  and 8.)
- Keep the task lane tiered and growing, not a flat pool, so a capability
  regression surfaces at a rung instead of being averaged away. (Discipline 9.)
- Enforce calibration and evaluation separation on the quantization and QLoRA
  tracks: the importance-matrix or LoRA calibration set stays disjoint from the
  held-out oracle tasks, and per-layer quant choices get logged, not summarized
  as one number. (Discipline 6.)
- Surface reasoning in receipts, not just pass or fail, so a reader follows the
  why. (Voice 8 and 10.)

## The one-line version

Lead with wonder, earn trust by trying to break things, and show your work so
the reader never has to take it on faith. That is the voice and the discipline,
and they are the same commitment pointed in two directions.

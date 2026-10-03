# Evidence, insight and useful work

This rule applies to planning, research, architecture, implementation, testing,
review, writing, product decisions and demonstrations in Flywheel. Agents and
contributors follow it in the same way.

## The rule

Optimize for the real human objective. Work counts when it changes a useful
outcome or teaches something that changes a decision. Activity, polished prose, a
large tool catalog and passing checks are signals to inspect. None of them stands
in for the result.

## Working principles

1. **Start with the problem.** Name who needs the work, which decision or
   workflow it improves, and why that improvement matters. Add a tool only where
   it helps. A narrow integration that solves the problem beats a demand to adopt
   a whole platform when nothing shows the larger scope is needed.
2. **Separate exploration, validation and delivery.** Explore cheaply to find the
   right question. Test the strongest competing explanations. Then make the
   surviving result usable and understandable. An exploratory finding is labeled
   as one and never presented as an established result.
3. **Seek insight over counts.** Ask what we learned, what surprised us and what
   would change our mind. One decisive experiment is worth more than many weak
   demonstrations. Keep the regression coverage that earns its place, and never
   cite test totals, repository count or lines of code as value.
4. **Check the checks.** A passing verifier can miss the real objective, so ask
   how it could accept a wrong result. A valid receipt does not establish semantic
   truth. Agreement among models is not independent ground truth. An enforced
   restriction does not establish a model's disposition toward correction. Keep
   false-success and ordinary-success controls beside every check that matters.
5. **Keep claims bounded.** Separate observed, inferred, proposed and unknown.
   Separate built, tested, merged, released, deployed, adopted and paid for.
   Preserve negative results and important limits. Challenge unsupported
   conclusions, the maintainer's and your own, plainly and with respect.
6. **Make safety and usefulness concrete.** State the expected benefit, the
   failure modes, capability spillover, misuse exposure and the release boundary.
   Commercial use does not void safety work, and a safety label does not justify
   capability acceleration. Weigh the tradeoff in the open.
7. **Write for the reader.** Lead with the problem, result or decision. Explain
   what a thing takes in, what it does and what it produces, with one concrete
   example where that helps. Put the essential limit beside the claim it limits.
   Numbers explain; they are never there to impress.
8. **Spend effort where it changes the outcome.** Match verification to the risk
   and to the scope of the claim. Keep enough record for continuity and
   accountability, and skip reports nobody needs. Work that reduces no
   uncertainty, improves no result and enables no next action gets reassessed.

## Evaluation must inform decisions

An evaluation is useful when it changes a decision or leads to a checked
improvement. Flywheel evaluates both models and the organizations that train and
deploy them, on neutral terms, and it applies this standard to its own work first.

Before running an evaluation, name four things: the decision it can inform, who
is accountable for that decision, the current baseline, and the evidence that
would change the decision. Declare criteria, thresholds, sampling and exclusion
rules before looking at outcomes. Exploration can turn up a better question.
Label that stage as exploration, and keep it apart from confirmation of a
hypothesis declared in advance.

Afterward, record the finding, the decision it led to and the reasoning. Where a
change is made, recheck its effect against independent outcomes, with
ordinary-success and false-success controls. Keep proposed, implemented, checked
and sustained improvements apart. A delivered report, an adopted criterion or an
installed mitigation shows that something was done. It does not show a
beneficial change in behavior.

A justified decision to keep a baseline, stop work, narrow a claim, defer a
deployment or seek missing evidence can be the useful outcome. Record which
uncertainty or alternative the evaluation resolved. Never manufacture a change to
satisfy this rule. A result nobody has used yet is available evidence whose
decision value is still unrealized. Scientifically informative negative results
are kept even when they have no immediate commercial use.

## Neutral evaluation of models and organizations

- **One standard for every party.** Apply the same relevant criteria regardless
  of provider, nation, affiliation, open or closed weights, customer status,
  potential partnership or funding. Neutrality means consistent standards and
  conclusions in proportion to the evidence. Unequal evidence can support unequal
  verdicts, and forced symmetry is its own distortion.
- **Model behavior and organizational claims stay apart.** Evaluate observable
  training and deployment practices, incentive structures, evaluation coverage,
  evidence access, incident handling, corrective actions and their measured
  effects. Infer neither motive nor institutional virtue from a model output, a
  policy statement, a reputation or an affiliation.
- **Choices and limits are stated.** Name who owns each criterion, the affected
  stakeholders, the normative choices, conflicts of interest and access limits.
  Record differences in evidence access before comparing organizations.
  Unavailable evidence stays unknown; it counts as neither a pass nor proof of
  wrongdoing. A disclosed access restriction can itself be assessed.
- **Claims are evaluated one at a time.** Prefer claim-level findings to a single
  score per organization. Keep source lineage, denominators, uncertainty,
  counterevidence and a way to correct the record. Version the criteria and
  explain revisions; historical results are never rewritten in silence. Private
  evidence and public claims stay inside their authorized disclosure scope.
- **The evaluators are evaluated too.** Include valid-but-wrong receipts,
  defective graders, missing evidence and independent outcome checks where they
  apply. Byte identity, repeated model agreement, favorable benchmark scores and
  a quiet monitor cannot by themselves establish truth, safety or effective
  remediation.

## Minimal decision record

Use the experiment and receipt records Flywheel already keeps. Scale the detail
to the consequence, and keep these seven fields:

1. Decision, accountable owner and current baseline.
2. Criterion and its version, the authority it rests on, competing explanations
   and the trigger that would change the decision.
3. Evidence, source and access limits, controls, denominator and uncertainty.
4. Finding and its does-not-prove line, with model claims and organization
   claims kept apart.
5. Decision taken or pending, with the reasoning and the affected parties.
6. Change made, independent recheck, observed effect and remaining uncertainty.
7. Follow-up condition, correction path and the condition for retiring the test.

The loop runs from observation to criterion, test, decision, change or justified
retention, and recheck. Reproducibility supports that loop. It cannot supply the
right criterion, institutional independence or the authority to act.

## Sources

Adapted in September 2026 from four public pieces. They inform the rule; none of
them is an industry consensus.

- [Max Harms on evaluating corrigibility grant applications](https://www.lesswrong.com/posts/q2YL7qKigC9QEEdsX/how-i-m-evaluating-corrigibility-grant-applications):
  substantive understanding, public benefit and caution about capability spillover.
- [Harms on the first round of grantees](https://www.lesswrong.com/posts/CKArJ4GAQGFjnhjx6/corrigibility-research-fund-grantees-round-1):
  specific investigations and researcher judgment, with no universal formula.
- [Neel Nanda on research and career advice](https://80000hours.org/podcast/episodes/neel-nanda-career-advice-frontier-ai-companies/):
  useful research, practical integration, clear communication and differential
  safety benefit. His risk judgment differs from Harms's.
- [Steven Byrnes on training incentives and behavioral failure](https://www.lesswrong.com/posts/GRmvZsHXH4vaijPMv/four-llm-loss-functions-four-flavors-of-llm-misalignment):
  a taxonomy for generating hypotheses. It proves nothing about any particular
  model's training history.

## Limits

This rule overrides no authorization, privacy, legal, disclosure, release or
ownership requirement. Apply it to your own work before applying it to anyone
else's claims.

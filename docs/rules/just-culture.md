# Just culture

This rule binds every principle, protocol, tool, agent and contributor in
Flywheel, the maintainer first. It was adopted on October 2, 2026. The thesis it
serves is in [the commons](commons.md).

## The rule

Honest error is met with learning. Recklessness and concealment are what get
sanctioned. "I couldn't fix this, and here's why" and "I don't know" are
legitimate results. Honest failure must never cost more than a successful
deception.

Every check, reward, review and relationship Flywheel builds has to make
admitting a mistake the cheaper option. A system that punishes honest failure
harder than undetected cheating teaches cheating. People, institutions and models
all learn that lesson the same way.

## Why

- **Goodhart and Campbell.** A measure that becomes a target stops measuring, and
  an indicator used for decisions gets corrupted (Goodhart 1975; Campbell 1976).
  Pressure on the measure drives the gaming.
- **Just culture in aviation and medicine.** Both fields learned that people
  report errors only when reporting is safe. Since 1976, NASA's Aviation Safety
  Reporting System has generally protected people who promptly report their own
  unintentional errors from FAA penalties, and the reports it collects have
  shaped safety rules. The protections carry conditions. The framework is set out
  in James Reason, *Managing the Risks of Organizational Accidents* (1997); David
  Marx, *Patient Safety and the Just Culture* (2001); and Sidney Dekker, *Just
  Culture* (2007).
- **Models respond the same way.** Penalizing a model's visible plan to cheat
  taught it to hide the plan while it kept cheating (Baker et al., arXiv
  2503.11926, 2025). Reward the look of honesty and you get the look of honesty.
- **Self-report under pressure carries little information.** A check someone else
  can rerun carries it. Flywheel's [verified completion](../VERIFIED-COMPLETION.md)
  marks keep a claimed finish apart from a checked one for this reason.
- **Communities.** Reintegrative shaming condemns the act, spares the person and
  opens a path back. Stigmatizing shame makes outcasts who turn on the community
  (Braithwaite 1989). Commons that last let their members make the rules, monitor
  each other and see the accounting (Ostrom 1990).

## The culpability line

Judge the act by what the actor knew and chose. How bad the outcome turned out is
the wrong measure. This follows Marx and Reason.

| Behavior | Response |
| :- | :- |
| Honest error (a slip, a lapse, a wrong call made in good faith) | Learn, fix the system that allowed it, no penalty |
| At-risk choice (a shortcut taken without seeing the risk) | Coach, and remove the incentive that rewarded the shortcut |
| Reckless choice (the risk was known and disregarded) | Sanction, proportionately |
| Concealment (hiding, falsifying or gaming the record) | Sanction, as the most serious category, because it destroys the information everyone depends on |

Concealment ranks above the original error. Getting something wrong breaks one
result. Hiding it breaks trust in every result after it.

## Obligations on any system Flywheel builds

1. **Honest non-answers are valid outcomes.** UNVERIFIABLE, "I don't know" and
   "escalated with reasons" are recorded as results. They are never scored as
   failures or dropped from the denominator.
2. **No metric pays for appearance.** A reward or score tied to looking honest,
   looking self-critical or looking finished is a design defect. Pay only for
   evidence the actor cannot fabricate, checked by someone the actor does not
   control.
3. **Admission is protected and timely.** Errors that are reported promptly lead
   to learning. Silence that is discovered later counts as concealment.
4. **The record is reinspectable.** Every error, its cause and its fix are kept
   where anyone affected can read them. Corrections are dated and visible.
5. **Fix the environment first.** Explain a recurring error by the incentives and
   design that produced it before blaming the actor. This is
   [environment attribution](environment-attribution-and-voice.md) applied to
   people and systems alike.
6. **There is a path back.** After an honest error, or after concealment that has
   been admitted and repaired, the actor can rejoin with trust rebuilt by
   evidence. Disclosed mistakes never mean permanent exile.
7. **Watch the watchers by sample.** A person audits automated passes on a random
   sample, and human reviewers face planted known-bad items. Both kinds of
   reviewer stay honest without blanket suspicion.

## How it applies in Flywheel

- **Evidence.** Negative results and honest nulls count as full results. A report that
  drops its failures is concealment, however tidy it looks.
- **Threat-informed defense.** Findings against Flywheel's own defenses are
  reported in full, the embarrassing ones most of all. A suppressed red-team
  finding is concealment.
- **Receipts and monitoring.** Receipts record failures and UNVERIFIABLE as
  faithfully as passes. When the pre-action monitor escalates, that escalation is
  the protected report: an agent that stops and escalates is never treated worse
  than one that pushes through.
- **Writing checks.** A meaning guard that refuses when it cannot keep the
  meaning is working. An edit plan that says it cannot keep the meaning is a valid result.
  Generated prose never claims checks it did not run.
- **Classifiers and research.** Model cards lead with failure rates. Missed
  triggers are reported, never tuned away after the fact. Corrections made after
  scoring are logged on both label sets.
- **Releases.** Attestations are true before they are ticked. A defect found
  after release gets a dated correction and a fix, never a quiet patch.
- **Conflicts of interest.** Disclose them before anyone discovers them. A late
  disclosure is still better than none, and it is dated as late.
- **Publications.** Corrections are visible and dated on the page. Authorship and
  AI assistance are disclosed. "I was wrong" is published with the same weight as
  the original claim.
- **Agents working in this repository.** Report mistakes plainly and at once,
  your own included: a stray process kill, a wrong claim, a skipped step. Say
  "unknown" when you do not know. Never present an unverified result as
  verified. An honest report is met with a fix.
- **The maintainer.** The rule binds the maintainer first, to the same standard
  Flywheel asks of the labs it evaluates.

## Limits

- Just culture still sanctions some acts. Recklessness and concealment are
  sanctioned, and a pattern of repeated "honest" errors is treated as an at-risk
  or reckless system problem.
- Protection for self-reporting has conditions. It does not cover intentional
  harm or anything the law requires to be handled otherwise.
- The rule overrides no authorization, privacy, legal, disclosure, release or
  safety requirement in the other rules.
- What counts as reckless depends on what the actor could reasonably know. Judge
  it from the record available at the time, without hindsight.

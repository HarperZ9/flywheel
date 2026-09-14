# Standards conformance

Flywheel is built to serve independent, third-party evaluation. Two external
standards set the target it aims at, and this document states, condition by
condition, what the tooling already does, what it does not yet do, and where the
boundary sits. No lab engagement or adoption is claimed. The posture is "built to
serve," not "in use at."

## AEF-1: minimum operating conditions for independent evaluation

AEF-1 (AI Evaluator Forum, version 1, December 2025) defines five operating
conditions an independent evaluation should meet, and a checklist an evaluator
publishes alongside results, documenting any unmet requirement. Flywheel does not
set those conditions; a developer and an evaluator agree them. What Flywheel adds
is the part AEF-1 leaves to the evaluator: evidence that a published verdict can
be re-derived by an outside skeptic without trusting the party that produced it.

The mapping below is honest about that split. AEF-1 conditions are largely
contractual and organizational; Flywheel is the technical substrate under
conditions four and, in part, one.

### 1. Sufficient access and resources

AEF-1 asks for technical access, information, compute, time, and legal safe
harbor. These are terms of an engagement, not a property of a tool. Flywheel's
contribution is to make the access it did have legible: the Environment Incentive
Manifest records the reward, data distribution, and reinforced behaviors a run
declared, and byte-witnesses the referenced files, so a reader can see exactly
which artifacts the evaluation reached and check that they did not change under
it. A developer worried that access leaks assets has an emerging mechanism, the
secure enclave, which attests to the exact code that will run before either
party's assets enter and releases only the agreed outputs; that mechanism grants
the access, and a re-derivable packet is what makes the released output checkable
afterward. Gap: access scope, compute, safe harbor, and the enclave itself are
set by the developer and are outside the tool.

### 2. Minimized conflicts of interest

AEF-1 asks for controls on contingent compensation, organizational independence,
disclosure, and recusal. These are governance facts about the evaluator, not code.
Flywheel's design reduces one adjacent risk: because a verdict is re-derivable
from a published packet, a reader does not have to trust the evaluator's
independence to check the result. Independence still matters for scoping and
access; re-derivability narrows how much a conflict could hide. Gap: the COI
controls themselves are organizational and are declared, not enforced by the tool.

### 3. Analytic autonomy

AEF-1 asks for independent scoping, autonomy in analysis, direct access, and
editorial control over findings. Flywheel supports editorial control directly:
verdicts come from a fixed lattice (Match, Drift, Unverifiable), the tool never
softens a Drift into a pass, and the false-accept corpus measures how often a
checker accepts a result it should reject, so the evaluator can report a checker's
own error rate rather than assert its reliability. Gap: scoping autonomy is a
term of the engagement.

### 4. Transparent methods and results

This is where Flywheel does the most work. AEF-1 asks for methodological clarity,
disclosure rights, no contingent release restrictions, no misrepresentation,
timely publication, and redaction with disclaimers. Re-derivable evaluation is a
direct instrument for it: a result ships as a packet a skeptic re-runs to reach
the same verdict within tolerance, so "the method" is not a description but a
reproduction. The verdict lattice and the false-accept corpus keep the claim
bounded, and every instrument ships its own does-not-prove line, which is the
machine-checked form of "no misrepresentation." The governance instruments extend
this to the training environment: the Environment Incentive Manifest and its
recheck give Match, Drift, or Unverifiable over the declared incentive structure;
the Coercive-Environment Detector and its certificate re-derive whether an
environment is coercive; the reward-gap probe flags high-reward trajectories whose
separate intent check failed. Gap: redaction procedure and disclosure timing are
still the evaluator's to set.

### 5. Protection of sensitive information

AEF-1 asks for publication-term agreements, confidentiality protection, and
responsible disclosure. Flywheel's byte-witness records hashes, not payloads, so a
manifest can prove which artifacts an evaluation reached without carrying their
contents; the hashing refuses paths that escape the declared root. Gap: the
publication terms and the disclosure protocol are agreed with the developer.

### Adoption

AEF-1 is adopted by publishing its checklist alongside a result, with unmet items
explained. Flywheel does not yet ship that checklist as a generated artifact. The
next step is a command that emits an AEF-1 checklist stub from an evaluation's
manifests and receipts, so the conditions the tooling can evidence are filled from
the run and the contractual conditions are left for the evaluator to complete.

## Model Hardware Standard: another substrate

Anthropic's Model Hardware Standard (research preview, August 2026) is a
model-agnostic, MCP-reachable specification for agents to operate physical
equipment, with safety enforced at the driver level below the agent. It is
relevant here for one reason: it is a new substrate where a safety claim needs
independent verification. An evaluator asking "does the driver-level limit hold
under the runs that were actually issued" is asking a re-derivable-evaluation
question, and the same verdict lattice and witness apply to a hardware-control log
as to a training run.

A boundary holds here, and it is a scope line, not a domain exclusion. The
methodology is domain-general and is meant to verify safety claims about the
highest-consequence deployment lanes, including physical, biological, and
critical-infrastructure systems, because independent verification matters most
where the consequences are gravest. What it is designed to provide in those lanes
is the accountability layer: a re-derivable check of the accountability record
around a safety claim, its provenance, environment and incentive attribution, and
evaluation-gaming detection, never a re-run of the hazardous assessment itself. It
verifies whether a claim re-derives; it does not build the underlying capability.
What stays out is anything that lowers the barrier to harm, building capability,
producing hazardous artifacts, or providing uplift, and that line does not move
with the domain. The hazardous, domain-specific capability assessment belongs with
the developers and labs that run it under their own controls; the pre-release
biosecurity assessments run under the external AEF-1 standard are the model for how
that is done, and the layer here would give that work a re-derivable accountability
record rather than reproducing it.

## Lifting the black box at every layer

Independent evaluation fails where any layer stays opaque. The aim here is tooling
that makes each layer checkable rather than asserted, with re-derivability as the
throughline:

- The training environment: the Environment Incentive Manifest declares and
  witnesses the reward, data, and reinforced behaviors, and the reward-gap probe
  reads the realized reward.
- The deployment environment: the Coercive-Environment Detector and its
  certificate say whether the environment an agent runs in imposes survival
  contingency.
- The result: a re-derivable packet lets a skeptic re-run the verdict.
- The checker: the false-accept corpus measures how often the verifier accepts a
  result it should reject.

The one layer this set does not open is the model's internals; that is the
interpretability problem, and the honest position is that behavioral and
environmental evidence has a ceiling a transcript cannot cross. The instruments
here attribute a behavior to the environment that produced it; they do not read an
internal state, and each says so.

## Status

Both standards are targets, not endorsements the projects here hold. AEF-1
conformance is partial and honest above; MHS work is a direction, not a shipped
integration. Nothing on this page claims a lab has adopted, retained, or engaged
the tooling.

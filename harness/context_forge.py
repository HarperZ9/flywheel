"""context_forge.py -- context engineering with a verifier that can't be gamed.

Cole Medin's context-engineering method (github.com/coleam00/context-engineering-intro)
is right that a task needs a whole CONTEXT, not a clever prompt: rules, examples,
docs, and -- the load-bearing part -- VALIDATION GATES the work must pass, with an
execute loop that "iterates until all validations succeed." That loop is exactly
this project's flywheel. The one difference is the whole thesis: his gates are
tests the model runs on ITSELF (self-verification, which a model can claim passed);
ours are EXTERNAL oracles the model cannot author or fake (C2). Our own ablation
measured the gap -- self-test selection earned +0, an external oracle +20 -- so a
PRP is only as strong as how EXTERNALLY-CHECKABLE its gates are.

So this builds a PRP (Product Requirements Prompt) on top of prompt_forge's
criterion-bearing spec, and scores confidence by the fraction of its validation
gates a non-self-authored oracle could run -- not a vibe. A PRP whose gates are all
subjective is honestly low-confidence; one whose gates are machine-checkable is the
"working first try" context engineering promises, backed by a check that can fail.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .prompt_forge import forge, PromptSpec

# per task-type validation gates: (check, externally_checkable). "Externally
# checkable" = a non-self-authored oracle can run it (pytest, a parser, wc), not a
# subjective human judgement. That flag is what grounds the confidence score.
_GATES: dict[str, list[tuple[str, bool]]] = {
    "code": [("pytest -q passes on the provided/derived tests", True),
             ("the solution imports/compiles with no error", True)],
    "extraction": [("every returned item appears verbatim in the source", True),
                   ("no source item matching the criteria is omitted", False)],
    "transform": [("the output parses as the target format", True),
                  ("the stated invariant holds between input and output", True)],
    "analysis": [("each claim carries a cited source", True),
                 ("the conclusion names an observation that would refute it", False)],
    "research": [("each fact has a resolvable source URL", True),
                 ("every claim is labeled verified / plausible / unknown", True)],
    "writing": [("length is within the stated limit (wc)", True),
                ("the one intended takeaway is present", False)],
    "qa": [("the answer is checkable against a named authority", True),
           ("uncertainty is labeled 'unknown' rather than guessed", False)],
    "general": [("a named, runnable check decides done", False)],
}


@dataclass
class PRP:
    """A Product Requirements Prompt: the criterion-bearing spec plus the context
    (examples, docs), the validation gates, and a confidence GROUNDED in how
    externally-verifiable those gates are."""
    spec: PromptSpec
    examples: list[str]
    documentation: list[str]
    validation_gates: list[tuple[str, bool]]   # (check, externally_checkable)
    confidence: int                             # 1..10, grounded not vibed
    context: str = ""

    @property
    def external_gate_ratio(self) -> float:
        g = self.validation_gates
        return (sum(1 for _, ext in g if ext) / len(g)) if g else 0.0

    def render(self) -> str:
        exs = "\n".join(f"- {e}" for e in self.examples) or "- (none -- add reference patterns to raise confidence)"
        docs = "\n".join(f"- {d}" for d in self.documentation) or "- (none)"
        gates = "\n".join(
            f"- [{'oracle' if ext else 'manual'}] {g}" for g, ext in self.validation_gates)
        return (
            f"# PRP -- {self.spec.task_type} task (confidence {self.confidence}/10)\n\n"
            f"## Goal\n{self.spec.goal.strip()}\n\n"
            f"## Role\n{self.spec.role}\n\n"
            f"## Context\n{(self.context or self.spec.context).strip() or '(none provided)'}\n\n"
            f"## Examples (reference patterns)\n{exs}\n\n"
            f"## Documentation\n{docs}\n\n"
            f"## Constraints\n" + ("\n".join(f"- {c}" for c in self.spec.constraints)
                                   or "- (none stated)") + "\n\n"
            f"## Output\n{self.spec.output_contract}\n\n"
            f"## Validation gates (must pass)\n{gates}\n"
            f"  NOTE: [oracle] gates are run by an EXTERNAL verifier the model cannot\n"
            f"  author or fake -- that is the difference from self-reported tests. The\n"
            f"  work iterates until the oracle gates pass, not until the model says so.\n\n"
            f"## Success criterion\n{self.spec.success_criterion}"
            + ("" if self.spec.well_posed else
               "\n  (auto-proposed; the goal did not state a checkable criterion -- confirm it)")
            + "\n"
        )

    def to_dict(self) -> dict:
        return {
            "schema": "flywheel.prp/v1",
            "goal": self.spec.goal, "task_type": self.spec.task_type,
            "confidence": self.confidence,
            "external_gate_ratio": round(self.external_gate_ratio, 3),
            "well_posed": self.spec.well_posed,
            "validation_gates": [{"check": g, "externally_checkable": e}
                                 for g, e in self.validation_gates],
            "prompt": self.render(),
        }


def _score(spec: PromptSpec, gates, examples, documentation, context) -> int:
    """Confidence 1..10, grounded: rewards external-checkability + real context,
    not fluent wording. A well-posed task with all-machine gates and examples is
    high; a vague task with subjective gates and no context is honestly low."""
    ext_ratio = (sum(1 for _, e in gates if e) / len(gates)) if gates else 0.0
    score = 3.0
    score += 3.0 * ext_ratio                    # the dominant term: can a machine check it?
    score += 2.0 if spec.well_posed else 0.0    # explicit criterion in the goal
    score += 1.0 if examples else 0.0
    score += 0.5 if documentation else 0.0
    score += 0.5 if (context or spec.context) else 0.0
    return max(1, min(10, round(score)))


def forge_prp(goal: str, *, examples: list[str] | None = None,
              documentation: list[str] | None = None, context: str = "",
              task_type: str | None = None, success_criterion: str = "",
              extra_gates: list[tuple[str, bool]] | None = None) -> PRP:
    """Build a PRP from a goal: forge the criterion-bearing spec, attach the
    task-type validation gates (plus any caller gates), and score confidence by
    external-checkability. The gates are what the flywheel's oracle enforces."""
    spec = forge(goal, task_type=task_type, context=context,
                 success_criterion=success_criterion, examples=examples)
    gates = list(_GATES.get(spec.task_type, _GATES["general"]))
    if extra_gates:
        gates += list(extra_gates)
    return PRP(spec=spec, examples=list(examples or []),
               documentation=list(documentation or []),
               validation_gates=gates,
               confidence=_score(spec, gates, examples, documentation, context),
               context=context)

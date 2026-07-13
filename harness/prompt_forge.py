"""prompt_forge.py -- turn a vague goal into a structured, criterion-bearing task.

The project's thesis: "a world already decided for the acting model makes it
perform better; the more it 'thinks', the dumber it gets." A good prompt IS that
pre-decided world -- it pins the role, the context, the constraints, the output
contract, and, above all, a CHECKABLE SUCCESS CRITERION the model did not author.
So this is not a template toy: it forces the same criterion-first discipline the
flywheel runs on. Give it a goal and it returns a prompt whose success is
verifiable -- and if the goal admits no checkable criterion, it says so and
proposes one, because an unverifiable task is the quiet failure of every
prompt-and-pray workflow.

Deterministic and zero-dep: it classifies the task, infers constraints from the
goal's own words, and assembles the prompt. No model call is required (an optional
refine hook can hand the draft to a proposer, but the criterion-forcing core is
rule-based so it never depends on the thing it is trying to make reliable).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# task-type signatures (first match wins; order = specificity)
_SIGNATURES = [
    ("code", ("implement", "function", "script", "code", "program", "algorithm",
              "class", "api", "endpoint", "regex", "parser", "fix ", "debug",
              "refactor", "bug")),
    ("extraction", ("extract", "parse", "pull out", "scrape", "identify the",
                    "list all", "find all", "get the fields")),
    ("transform", ("convert", "transform", "translate", "reformat", "summarize",
                   "rewrite", "rephrase", "compress", "shorten")),
    ("analysis", ("analyze", "evaluate", "compare", "assess", "review", "critique",
                  "examine", "audit", "diagnose", "root cause")),
    ("research", ("research", "investigate", "find out", "survey", "explore",
                  "sources", "state of the art", "literature")),
    ("writing", ("write", "draft", "compose", "essay", "article", "email",
                 "letter", "story", "blog", "post", "copy")),
    ("qa", ("explain", "what is", "why does", "how do", "how does", "answer",
            "describe", "define")),
]

_ROLE = {
    "code": "a precise senior engineer who writes the smallest correct solution and nothing else",
    "extraction": "a careful information extractor who returns only what the source supports",
    "transform": "an exact transformer who conserves meaning and changes only what is asked",
    "analysis": "a grounded analyst who cites evidence for every claim and states uncertainty",
    "research": "a rigorous researcher who separates verified fact from speculation and cites sources",
    "writing": "a disciplined writer who serves the reader and cuts everything that does not",
    "qa": "a clear explainer who answers exactly what was asked, no more",
    "general": "a careful assistant who does exactly the task and states what it cannot verify",
}

_OUTPUT = {
    "code": "ONLY the code (a single runnable unit), no prose, no fences unless asked.",
    "extraction": "the extracted items in the requested structure; nothing invented, absences marked.",
    "transform": "only the transformed artifact; the invariant that must be preserved stated once.",
    "analysis": "a claim -> evidence table, then a one-line falsifiable conclusion.",
    "research": "findings with a source per claim; label each verified / plausible / unknown.",
    "writing": "the finished piece at the target length; no meta-commentary.",
    "qa": "the direct answer first, then the minimum support; say 'unknown' rather than guess.",
    "general": "exactly the requested artifact; nothing extra.",
}

_CRITERION = {
    "code": "the solution passes its tests (provide/derive at least one concrete input->expected assertion)",
    "extraction": "every returned item is present in the source and no source item that matches is missed",
    "transform": "the stated invariant is preserved and a third party can re-derive the output from the input",
    "analysis": "each claim has cited evidence and the conclusion states an observation that would refute it",
    "research": "each claim carries a source and a verified/plausible/unknown label; no unlabeled assertion",
    "writing": "the piece meets the length/format target and a reader gets the one intended takeaway",
    "qa": "the answer is directly checkable against a named authority, or is labeled 'unknown'",
    "general": "a named, checkable condition decides done -- if none exists, the task is not yet well-posed",
}

# constraint sniffers: (regex, template) -- pull explicit constraints from the goal
_CONSTRAINT_PATTERNS = [
    (re.compile(r"\bin (python|javascript|typescript|rust|go|c\+\+|java|sql)\b", re.I),
     lambda m: f"language: {m.group(1)}"),
    (re.compile(r"\b(under|less than|<=?|at most)\s+(\d+)\s+(words|characters|chars|lines|tokens)\b", re.I),
     lambda m: f"length: at most {m.group(2)} {m.group(3)}"),
    (re.compile(r"\b(no dependencies|zero-dep|stdlib only|pure python)\b", re.I),
     lambda m: "no external dependencies (stdlib only)"),
    (re.compile(r"\b(json|csv|yaml|markdown|table|bullet)\b", re.I),
     lambda m: f"output format: {m.group(1).lower()}"),
    (re.compile(r"\bfor (beginners|a child|an expert|a cto|non-technical)\b", re.I),
     lambda m: f"audience: {m.group(1)}"),
]


@dataclass
class PromptSpec:
    goal: str
    task_type: str
    role: str
    context: str
    constraints: list[str]
    output_contract: str
    success_criterion: str
    criterion_source: str            # "derived-from-goal" | "auto-proposed"
    well_posed: bool                 # False if no checkable criterion could be pinned
    examples: list[str] = field(default_factory=list)

    def render(self) -> str:
        cons = "\n".join(f"- {c}" for c in self.constraints) or "- (none stated; ask if a real constraint is missing)"
        ex = ("\n\n# Examples\n" + "\n".join(f"- {e}" for e in self.examples)) if self.examples else ""
        flag = ("" if self.criterion_source == "derived-from-goal"
                else "\n  (auto-proposed -- the goal did not state a checkable criterion; confirm or replace it)")
        return (
            f"# Role\nYou are {self.role}.\n\n"
            f"# Task\n{self.goal.strip()}\n\n"
            f"# Context\n{self.context.strip() or '(none provided)'}\n\n"
            f"# Constraints\n{cons}\n\n"
            f"# Output\n{self.output_contract}{ex}\n\n"
            f"# Success criterion (the check that must pass)\n{self.success_criterion}{flag}\n"
        )

    def to_dict(self) -> dict:
        return {
            "schema": "flywheel.prompt-spec/v1",
            "goal": self.goal, "task_type": self.task_type,
            "constraints": self.constraints,
            "success_criterion": self.success_criterion,
            "criterion_source": self.criterion_source,
            "well_posed": self.well_posed,
            "prompt": self.render(),
        }


def classify_task(goal: str) -> str:
    g = (goal or "").lower()
    for name, sig in _SIGNATURES:
        if any(s in g for s in sig):
            return name
    return "general"


def _sniff_constraints(goal: str) -> list[str]:
    out = []
    for rx, tmpl in _CONSTRAINT_PATTERNS:
        m = rx.search(goal or "")
        if m:
            out.append(tmpl(m))
    return out


def _derive_criterion(goal: str, task_type: str) -> tuple[str, str, bool]:
    """Return (criterion, source, well_posed). If the goal itself names a check
    ('passes the tests', 'sorted', 'matches X'), use it; else auto-propose the
    task-type default and flag the goal as not-yet-well-posed."""
    g = (goal or "").lower()
    explicit = [
        (r"pass(es|ing)? .*test", "the solution passes the stated tests"),
        (r"sorted|in order", "the output is correctly ordered per the stated rule"),
        (r"matches?|equal to|same as", "the output matches the stated reference exactly"),
        (r"under \d+|at most \d+|no more than \d+", "the output satisfies the stated size limit"),
        (r"valid (json|xml|yaml|csv)", "the output parses as the stated valid format"),
    ]
    for pat, crit in explicit:
        if re.search(pat, g):
            return crit, "derived-from-goal", True
    return _CRITERION.get(task_type, _CRITERION["general"]), "auto-proposed", False


def forge(goal: str, *, task_type: str | None = None, context: str = "",
          output_contract: str = "", success_criterion: str = "",
          examples: list[str] | None = None) -> PromptSpec:
    """Build a structured, criterion-bearing PromptSpec from a goal. Any field the
    caller supplies overrides the inferred default; the criterion is the one that
    is forced -- if the caller gives none and the goal implies none, it is
    auto-proposed and the spec is flagged not-well-posed."""
    goal = goal or ""
    tt = task_type or classify_task(goal)
    if success_criterion:
        crit, src, posed = success_criterion, "derived-from-goal", True
    else:
        crit, src, posed = _derive_criterion(goal, tt)
    return PromptSpec(
        goal=goal, task_type=tt,
        role=_ROLE.get(tt, _ROLE["general"]),
        context=context,
        constraints=_sniff_constraints(goal),
        output_contract=output_contract or _OUTPUT.get(tt, _OUTPUT["general"]),
        success_criterion=crit, criterion_source=src, well_posed=posed,
        examples=list(examples or []))


def forge_prompt(goal: str, **kw) -> str:
    """Convenience: return the rendered prompt string directly."""
    return forge(goal, **kw).render()

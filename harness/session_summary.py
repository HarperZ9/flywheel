"""Four-question run summaries whose factual half is derived, not narrated.

A summary written entirely by the thing being summarized is a claim about a
claim. This module answers the four questions an operator actually asks at the
end of a stretch of work, and separates what the repository can prove from what
the agent asserts:

1. What did we set out to do?
2. What did we do?
3. What is left to finish this work?
4. What decisions are needed?

Every answer carries a ``basis``. ``derived`` items come from git and from the
receipt store. ``stated`` items come from whoever ran the command. ``mixed``
means both, ``unknown`` means neither had anything. The point of the split is
the last step: when a stated answer claims the work is finished and the derived
evidence shows uncommitted files or unpushed commits, that contradiction is
recorded in ``disagreements`` and the verdict changes. A summary cannot claim
more than the tree supports.

Three scopes set the commit window:

``task``     the head commit plus the working tree, for one unit of work.
``goal``     base..HEAD plus the working tree, for the branch.
``session``  the goal window plus receipts written since ``--since``.

A run that checked its own output against the sources that decide it leaves a
validation ledger, and ``--validation-ledger`` folds that into the third
answer. What went out held is not finished work, whoever says otherwise.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess

from .summary_validation import HOLD, read_validation, validation_answers

SCHEMA = "harness.session-summary/v1"
SCOPES = ("task", "goal", "session")
BASIS = ("derived", "stated", "mixed", "unknown")
QUESTIONS = (
    ("intent", "What did we set out to do?"),
    ("did", "What did we do?"),
    ("remaining", "What is left to finish this work?"),
    ("decisions", "What decisions are needed?"),
)
_MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_MARKER_LIMIT = 20


def _git(root: Path, *args: str) -> str:
    """Run one read-only git command, returning "" rather than raising."""
    try:
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def resolve_base(root: Path, base: str) -> str:
    """Pick the ref the branch is measured against."""
    if base:
        return base
    for candidate in ("origin/main", "main", "origin/master", "master"):
        if _git(root, "rev-parse", "--verify", "--quiet", candidate):
            return candidate
    return ""


def _markers(root: Path, window: str) -> list[dict[str, str]]:
    """Attention markers this window ADDED, so old debt is not re-reported."""
    rows: list[dict[str, str]] = []
    path = ""
    for line in _git(root, "diff", "-U0", window).splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and _MARKER.search(line):
            rows.append({"path": path, "text": line[1:].strip()[:160]})
            if len(rows) >= _MARKER_LIMIT:
                break
    return rows


def _worktree(root: Path) -> dict[str, list[str]]:
    staged, unstaged, untracked = [], [], []
    for line in _git(root, "status", "--porcelain=v1").splitlines():
        code, name = line[:2], line[3:].strip()
        if code == "??":
            untracked.append(name)
            continue
        if code[0] not in " ?":
            staged.append(name)
        if code[1] not in " ?":
            unstaged.append(name)
    return {"staged": sorted(staged), "unstaged": sorted(unstaged), "untracked": sorted(untracked)}


def _upstream(root: Path) -> dict[str, object]:
    ref = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not ref:
        return {"ref": "", "state": "no_upstream", "ahead": 0, "behind": 0}
    counts = _git(root, "rev-list", "--left-right", "--count", f"{ref}...HEAD").split()
    behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    return {"ref": ref, "state": "tracked", "ahead": ahead, "behind": behind}


def _receipts(store_root: Path, since: str) -> list[dict[str, str]]:
    """Receipt kinds and verdicts written since ``since``, metadata only."""
    if not store_root.is_dir():
        return []
    cutoff = since.strip()
    rows: list[dict[str, str]] = []
    for path in sorted(store_root.rglob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(body, dict) or "kind" not in body:
            continue
        stamp = str(body.get("created_at", "") or body.get("timestamp", ""))
        if cutoff and stamp < cutoff:
            continue
        rows.append({"kind": str(body.get("kind", "")), "verdict": str(body.get("verdict", "")),
                     "run_id": str(body.get("run_id", "")), "created_at": stamp})
    return rows


def collect_evidence(root: Path, *, scope: str, base: str = "", since: str = "",
                     store_root: str = "", validation_ledger: str = "") -> dict[str, object]:
    """Everything the repository can say about this window without being told."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope: {scope}")
    root = Path(root).resolve(strict=True)
    head = _git(root, "rev-parse", "HEAD")
    resolved_base = "HEAD~1" if scope == "task" else resolve_base(root, base)
    window = f"{resolved_base}..HEAD" if resolved_base else ""
    commits = []
    for line in (_git(root, "log", "--format=%h%x1f%s", window) if window else "").splitlines():
        sha, _, subject = line.partition("\x1f")
        commits.append({"sha": sha, "subject": subject})
    changed = [name for name in (_git(root, "diff", "--name-only", window) if window else "").splitlines() if name]
    return {"scope": scope, "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "head": head, "base": resolved_base, "window": window,
            "commits": commits, "changed_files": sorted(changed),
            "worktree": _worktree(root), "upstream": _upstream(root),
            "markers": _markers(root, window) if window else [],
            "receipts": _receipts(Path(store_root), since) if (scope == "session" and store_root) else [],
            "validation": read_validation(validation_ledger, since=since) if validation_ledger else []}


def derive_answers(evidence: dict) -> dict[str, list[str]]:
    """The four answers, insofar as the repository already knows them."""
    worktree, upstream = dict(evidence["worktree"]), dict(evidence["upstream"])
    dirty = sum(len(worktree[key]) for key in ("staged", "unstaged", "untracked"))
    intent = []
    if evidence["branch"]:
        intent.append(f"branch under work: {evidence['branch']}")
    did = [f"{commit['sha']} {commit['subject']}" for commit in evidence["commits"]]
    if evidence["changed_files"]:
        did.append(f"{len(evidence['changed_files'])} file(s) changed across the window {evidence['window']}")
    for row in evidence["receipts"]:
        did.append(f"receipt {row['kind']} -> {row['verdict'] or 'no verdict'}")
    remaining, decisions = [], []
    if dirty:
        remaining.append(f"{dirty} uncommitted path(s): "
                         + ", ".join(sorted(worktree["staged"] + worktree["unstaged"] + worktree["untracked"])[:8]))
        decisions.append("commit, stash, or discard the uncommitted paths")
    if int(upstream.get("ahead", 0)):
        remaining.append(f"{upstream['ahead']} commit(s) not on {upstream['ref']}")
        decisions.append(f"push the branch to {upstream['ref']}, or say it stays local")
    if upstream.get("state") == "no_upstream" and evidence["commits"]:
        remaining.append("branch has no upstream, so nothing here is on a remote")
        decisions.append("choose a remote for this branch, or confirm it is local only")
    if int(upstream.get("behind", 0)):
        decisions.append(f"rebase or merge {upstream['behind']} commit(s) from {upstream['ref']}")
    for marker in evidence["markers"]:
        remaining.append(f"marker added in {marker['path']}: {marker['text']}")
    from_ledger = validation_answers(list(evidence.get("validation") or []))
    return {"intent": intent, "did": did + from_ledger["did"],
            "remaining": remaining + from_ledger["remaining"],
            "decisions": decisions + from_ledger["decisions"]}


def _basis(derived: list[str], stated: list[str]) -> str:
    if derived and stated:
        return "mixed"
    if derived:
        return "derived"
    return "stated" if stated else "unknown"


def find_disagreements(derived: dict[str, list[str]], stated: dict[str, list[str]],
                       evidence: dict | None = None) -> list[dict[str, str]]:
    """Where the narrated answer claims more than the tree supports.

    Every class here is structural. None of them reads the prose of a stated
    answer, because a keyword in a sentence is not evidence and a summary that
    graded wording would fail honest writing and pass a careful liar.
    """
    rows = []
    facts = evidence or {}
    if stated.get("remaining") == [] and "remaining" in stated and derived["remaining"]:
        rows.append({"question": "remaining", "code": "claimed_finished_with_work_outstanding",
                     "detail": f"{len(derived['remaining'])} derived item(s) remain"})
    if stated.get("decisions") == [] and "decisions" in stated and derived["decisions"]:
        rows.append({"question": "decisions", "code": "claimed_no_decisions_with_blockers",
                     "detail": f"{len(derived['decisions'])} derived decision(s) stand"})
    held = [row for row in (facts.get("validation") or []) if row.get("release") == HOLD]
    if held and stated.get("remaining") == []:
        # Held output is a different fact from unfinished work: the answer was
        # checked and it disagreed with the source that decides it. Reporting
        # that under the same code would let it read as one more loose end.
        rows.append({"question": "remaining", "code": "claimed_finished_with_output_held",
                     "detail": f"{len(held)} check(s) held: "
                               + ", ".join(str(row.get("subject") or "no subject") for row in held[:4])})
    worktree = dict(facts.get("worktree") or {})
    untouched = (not facts.get("commits")
                 and not any(worktree.get(key) for key in ("staged", "unstaged", "untracked")))
    if stated.get("did") and facts and untouched:
        rows.append({"question": "did", "code": "claimed_work_with_nothing_in_the_tree",
                     "detail": f"{len(stated['did'])} stated item(s) over an empty window "
                               f"`{facts.get('window') or 'none'}` and a clean tree"})
    return rows


def build_session_summary(root: Path, *, scope: str, base: str = "", since: str = "",
                          store_root: str = "", validation_ledger: str = "",
                          statements: dict | None = None) -> dict:
    """The whole record: evidence, four answers, and any contradiction between them."""
    evidence = collect_evidence(root, scope=scope, base=base, since=since,
                                store_root=store_root, validation_ledger=validation_ledger)
    derived = derive_answers(evidence)
    stated = {key: [str(item) for item in value] for key, value in (statements or {}).items() if key in derived}
    answers = []
    for key, prompt in QUESTIONS:
        answers.append({"key": key, "question": prompt, "basis": _basis(derived[key], stated.get(key, [])),
                        "derived": derived[key], "stated": stated.get(key, [])})
    disagreements = find_disagreements(derived, stated, evidence)
    return {"schema": SCHEMA, "scope": scope,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "evidence": evidence, "answers": answers, "disagreements": disagreements,
            "verdict": "SUMMARY_DISAGREES" if disagreements else "SUMMARY_RECORDED",
            "does_not_prove": [
                "A derived answer reports repository state, not whether the work is correct.",
                "A stated answer is an assertion by whoever ran this command and is not checked.",
                "An empty disagreement list means no contradiction was tested for, not that none exists.",
                "A ledger read here reports what a check decided; it does not re-run the check."]}


def render_markdown(summary: dict) -> str:
    """The operator-facing view: four questions, each answer labelled by basis."""
    evidence = summary["evidence"]
    lines = [f"# Run summary ({summary['scope']})", "",
             f"- branch: `{evidence['branch']}` at `{evidence['head'][:12]}`",
             f"- window: `{evidence['window'] or 'none'}`",
             f"- verdict: **{summary['verdict']}**", ""]
    for answer in summary["answers"]:
        lines += [f"## {answer['question']}", "", f"_basis: {answer['basis']}_", ""]
        if not answer["derived"] and not answer["stated"]:
            lines += ["Nothing recorded.", ""]
            continue
        lines += [f"- {item} (derived)" for item in answer["derived"]]
        lines += [f"- {item} (stated)" for item in answer["stated"]]
        lines.append("")
    rows = list(evidence.get("validation") or [])
    if rows:
        short = [row for row in rows if row.get("release") != "RELEASE"]
        lines += ["## Output validation", "",
                  f"{len(rows)} check(s) recorded, {len(short)} short of a clean release.", ""]
        for row in short[:10]:
            named = list(row.get("blocking") or []) or list(row.get("unresolved") or [])
            lines.append(f"- `{row.get('release')}` {row.get('scope')}/"
                         f"{row.get('subject') or 'no subject'}: "
                         + (", ".join(str(item) for item in named[:4]) or "no field named"))
        lines.append("")
    if summary["disagreements"]:
        lines += ["## Disagreements", ""]
        lines += [f"- `{row['code']}` on {row['question']}: {row['detail']}" for row in summary["disagreements"]]
        lines.append("")
    lines += ["## What this does not prove", ""]
    lines += [f"- {item}" for item in summary["does_not_prove"]]
    return "\n".join(lines) + "\n"

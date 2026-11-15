"""The resume brief: priority order, strict-prefix truncation with a report,
per-target budgets, a deterministic receipt, and project isolation."""
from __future__ import annotations

import hashlib
import json

import pytest

from canon.workspace import authoring
from canon.workspace.brief import BudgetError, make_brief
from canon.workspace.identity import derive_identity
from canon.workspace.moves import promote
from canon.workspace.pool import TaggedRecord, project_pool
from canon.workspace.store import ProjectStore
from canon.workspace.targets import TARGETS, target_for

from ._workspace_helpers import block, init_repo


def _fill(store: ProjectStore) -> None:
    store.put(authoring.focus(store, goal="Ship the handoff command",
                              areas=["src/canon/workspace"], branch="feat/handoff"))
    store.put(authoring.work_item(store, title="Write the tests"))
    store.put(authoring.work_item(store, title="Port the renderer", status="in-progress"))
    store.put(authoring.work_item(store, title="Old chore", status="done"))
    store.put(authoring.decision(store, title="Row format", decision_text="JSONL rows",
                                 context="Stores must diff", rejected=[("SQLite", "binary diffs")]))
    store.put(authoring.decision(store, title="Brief order", decision_text="Focus first",
                                 context="The next agent reads top down"))
    store.put(authoring.constraint(store, statement="Tests pass on Windows",
                                   category="quirk", reason="CI runs both"))
    store.put(block("voice", "Plain technical English.", 99))


@pytest.fixture()
def project(tmp_path):
    ident = derive_identity(init_repo(tmp_path / "repo", "https://github.com/o/repo"))
    store = ProjectStore(tmp_path / "store", ident)
    _fill(store)
    return ident, store


def _brief(project, target="markdown", **kw):
    ident, store = project
    return make_brief(ident, project_pool(store), target_for(target), **kw)


def test_the_brief_reads_focus_then_work_then_decisions_then_constraints(project):
    text = _brief(project).text
    order = [text.index(h) for h in ("## Focus", "## Open work", "## Decisions",
                                     "## Constraints and quirks")]
    assert order == sorted(order)
    assert text.index("Port the renderer") < text.index("Write the tests")
    assert text.index("Brief order") < text.index("Row format")
    assert "Rejected: SQLite. Reason: binary diffs" in text
    assert "Branch: feat/handoff" in text
    assert "Old chore" not in text and "Plain technical English." not in text


def test_records_excluded_by_rule_are_named_in_the_receipt(project):
    receipt = _brief(project).receipt
    reasons = {e["id"]: e["reason"] for e in receipt["excluded"]}
    assert reasons["voice"].startswith("instruction block")
    assert any(r == "closed work item" for r in reasons.values())
    assert receipt["left_out"] == []


def test_the_same_pool_gives_the_same_bytes(project, tmp_path):
    ident, store = project
    first = _brief(project)
    again = _brief(project)
    assert first.text == again.text and first.receipt == again.receipt
    assert first.receipt["brief"]["sha256"] == \
        hashlib.sha256(first.text.encode("utf-8")).hexdigest()


def test_a_tight_budget_keeps_a_strict_prefix_and_reports_the_rest(project):
    full = _brief(project)
    budget = len(full.text.encode("utf-8")) - 200
    tight = _brief(project, budget_bytes=budget)
    assert len(tight.text.encode("utf-8")) <= budget
    assert tight.left_out, "the budget should force a cut"
    assert "## Left out" in tight.text
    order = [i.record.id for i in full.included]
    kept = [i.record.id for i in tight.included]
    assert kept == order[:len(kept)]
    cut = [entry["id"] for entry in tight.receipt["left_out"]]
    assert cut == order[len(kept):]
    for item in tight.left_out:
        assert item.record.id in tight.text or "more" in tight.text


def test_a_line_budget_is_honoured_too(project):
    brief = _brief(project, budget_lines=14)
    assert brief.text.count("\n") <= 14
    assert brief.receipt["target"]["budget_lines"] == 14


def test_a_budget_too_small_for_the_header_is_refused(project):
    with pytest.raises(BudgetError):
        _brief(project, budget_bytes=40)


@pytest.mark.parametrize("target", [t.name for t in TARGETS])
def test_every_target_keeps_its_brief_inside_its_budget(project, target):
    ident, store = project
    pool = project_pool(store)
    for n in range(300):
        rec = authoring.build("environment-constraint", f"constraint-x{n}",
                              {"statement": f"Constraint number {n} " * 8,
                               "category": "constraint"}, 1000 + n)
        pool.append(TaggedRecord(ident.project_id, rec))
    brief = make_brief(ident, pool, target_for(target))
    spec = target_for(target)
    assert len(brief.text.encode("utf-8")) <= spec.brief_bytes
    assert brief.text.count("\n") <= spec.brief_lines
    assert brief.left_out and brief.receipt["target"]["name"] == target


def test_contamination_control_another_project_never_reaches_this_brief(project, tmp_path):
    ident, store = project
    other = ProjectStore(store.root, derive_identity(init_repo(tmp_path / "other",
                                                               "https://github.com/o/other")))
    other.put(authoring.work_item(other, title="Other project secret task"))
    brief = make_brief(ident, project_pool(store), target_for("codex"))
    assert "Other project secret task" not in brief.text
    assert "Other project secret task" not in json.dumps(brief.receipt)
    declared = (other.project_id,)
    named = make_brief(ident, project_pool(store, include_projects=declared),
                       target_for("codex"), declared=declared)
    assert f"Other project secret task (task-1) [from {other.project_id}]" in named.text
    assert named.receipt["declared_projects"] == [other.project_id]


def test_a_promoted_record_shows_as_global(project):
    ident, store = project
    decision_id = next(r.id for r in store.records() if r.data.get("title") == "Row format")
    promote(store, decision_id, reason="house rule")
    assert "Row format [accepted] (" in _brief(project).text
    assert "[global]" in _brief(project).text

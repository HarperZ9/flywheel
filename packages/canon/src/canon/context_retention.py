"""Retention: canon's retention planner (retention.py) applied to the context store.

A policy file names captured events, each with one planner action. The planner
validates each entry, and each action becomes a purge target: `tombstone` and
`purge-all` remove the event and its derived records, and, as a purge does, the
paired answer unless the file sets `keep_responses`; `purge-derived` removes
only the derived records, which the policy must cover by naming the `sqlite`
store; `retain` keeps everything. A run is one purge plan, confirmed by its
digest like any other, and each tombstone names the rule as its reason code.

An event an earlier run already purged is listed as already purged, so a
policy can run again after it applied. A policy that retains an answer, or
purges only its derived records, while another entry removes that answer with
its prompt is refused; `keep_responses` is the way to keep answers.

A policy that asks a tombstone to keep a content hash is refused: context
tombstones hold none, so nothing kept after a purge confirms what it removed.
"""
from __future__ import annotations

from .context_purge import ContextPurgeError, ContextPurgeNotFound, Selection, Target, was_purged
from .retention import DerivedArtifactRef, RetentionPolicy, plan_retention, validate_retention_policy

POLICY_SCHEMA = "canon.context-retention-policy/v1"
_REASONS = {"tombstone": "retention_tombstone", "purge-all": "retention_purge_all",
            "purge-derived": "retention_purge_derived"}
_POLICY_KEYS = {"schema", "keep_responses", "policies"}
_ENTRY_KEYS = {"subject_id", "action", "retain_content_hash", "derived_stores"}


def policy_selection(policy) -> Selection:
    """A purge selection from a parsed policy file; refuses a malformed one."""
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise ContextPurgeError(f"a retention policy needs schema {POLICY_SCHEMA}")
    if set(policy) - _POLICY_KEYS:
        raise ContextPurgeError("a retention policy holds only schema, keep_responses and policies")
    keep = policy.get("keep_responses", False)
    if type(keep) is not bool:
        raise ContextPurgeError("keep_responses must be true or false")
    entries = policy.get("policies")
    if not isinstance(entries, list) or not entries:
        raise ContextPurgeError("a retention policy needs at least one entry in policies")
    rules = [_rule(entry, index) for index, entry in enumerate(entries)]
    if len({rule.subject_id for rule in rules}) != len(rules):
        raise ContextPurgeError("a retention policy names the same event twice")
    description = {"policy": {"schema": POLICY_SCHEMA, "keep_responses": keep, "policies": [
        {"subject_id": rule.subject_id, "action": rule.action,
         "retain_content_hash": rule.retain_content_hash,
         "derived_stores": list(rule.derived_stores)} for rule in rules]}}
    return Selection(description, keep, lambda view: _targets(view, rules, keep))


def _rule(entry, index: int) -> RetentionPolicy:
    if not isinstance(entry, dict) or set(entry) - _ENTRY_KEYS:
        raise ContextPurgeError(f"retention policy entry {index} has unknown fields")
    stores = entry.get("derived_stores", [])
    rule = RetentionPolicy(entry.get("subject_id"), entry.get("action"),
                           entry.get("retain_content_hash", False),
                           tuple(stores) if isinstance(stores, list) else stores)
    violations = validate_retention_policy(rule)
    if violations:
        raise ContextPurgeError(f"retention policy entry {index} is invalid: "
                                + ", ".join(violations))
    if rule.retain_content_hash:
        raise ContextPurgeError("a context tombstone keeps no content hash; "
                                "set retain_content_hash to false")
    return rule


def _targets(view, rules: list[RetentionPolicy], keep: bool) -> list[Target]:
    targets = []
    for rule in rules:
        if rule.subject_id not in view.events:
            if not was_purged(view, rule.subject_id):
                raise ContextPurgeNotFound("a retention policy names an event that is not "
                                           "captured in this workspace and project")
            if rule.action != "retain":
                targets.append(Target(rule.subject_id, "event", _REASONS[rule.action]))
            continue
        refs = tuple(DerivedArtifactRef("sqlite", key, None, True)
                     for key in view.derived.get(rule.subject_id, []))
        planned = plan_retention(rule.subject_id, policy=rule, derived_refs=refs,
                                 content_sha256=None)
        if not planned.ok:
            raise ContextPurgeError("the retention planner refused an entry: "
                                    + ", ".join(planned.violations))
        if rule.action != "retain":
            mode = "derived" if rule.action == "purge-derived" else "event"
            targets.append(Target(rule.subject_id, mode, _REASONS[rule.action]))
    if not keep:
        _refuse_kept_answers_in_a_closure(view, rules, targets)
    return targets


def _refuse_kept_answers_in_a_closure(view, rules, targets) -> None:
    """An entry that retains an answer, or purges only its derived records,
    cannot stand beside an entry that removes the answer with its prompt."""
    removed = {answer for target in targets if target.mode == "event"
               for answer in view.answers.get(target.event_id, [])}
    kept = {rule.subject_id for rule in rules if rule.action in ("retain", "purge-derived")}
    if removed & kept:
        raise ContextPurgeError("a retention policy keeps an answer that another entry removes "
                                "with its prompt; set keep_responses to true or change one entry")

"""registry.py -- which criteria exist, which may mint rewards, what a change voids.

Plain JSON on disk, so a fork edits data rather than Python and a reader who
never runs this code can still audit what was registered.

Three disciplines the registry enforces rather than trusts:

  1. **Append-only.** A superseded criterion stays readable and an invalidated
     one is marked, never removed. A record that can be tidied is not a record.
  2. **No id reuse without lineage.** Registering different content under an
     existing id is refused. Otherwise "criterion X" means two things and every
     receipt citing it becomes ambiguous. The legitimate route is amend(), which
     carries the parent hash.
  3. **Ineligible is registered, not rejected.** A criterion that cannot mint a
     reward (interpretive domain, non-conjunctive rule) is still admitted for
     evaluation and marked with a typed reason. Refusing it outright would push
     people to lie about the domain to get registered, which is the opposite of
     what the fence is for.

Incumbents are held here too, with their sourcing requirement: a published bound
needs two independent citations, and an operator-computed one needs none but must
say so. Values are decimal strings, never floats, because cross-platform float
formatting is the likeliest way a stranger's replay disagrees over nothing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

from .spec import Criterion, CriterionError

SCHEMA = "flywheel.criterion-registry/v1"
PUBLISHED_SOURCES = frozenset({"published_table"})
CITATIONS_REQUIRED = 2


class RegistryError(ValueError):
    """The registry refuses to hold something that would make it ambiguous."""


class InvalidationCode(str, Enum):
    CRITERION_AMENDED = "CRITERION_AMENDED"
    REFERENCE_SET_REVISED = "REFERENCE_SET_REVISED"
    PROVISION_UPGRADED = "PROVISION_UPGRADED"
    SCOPE_VIOLATED = "SCOPE_VIOLATED"
    ORACLE_QA_FAILED = "ORACLE_QA_FAILED"
    EXPLOIT_DISCOVERED = "EXPLOIT_DISCOVERED"
    THIRD_PARTY_DISPUTE = "THIRD_PARTY_DISPUTE"
    SCHEMA_MIGRATED = "SCHEMA_MIGRATED"


@dataclass
class Incumbent:
    criterion_id: str
    value: str                       # decimal string, never a float
    source: str                      # published_table | operator_search | none
    citations: list[str] = field(default_factory=list)
    provenance_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Registry:
    """A JSON-backed, append-only criterion registry."""

    def __init__(self, path: Path):
        self.path = Path(path)

    # --- storage -------------------------------------------------------------

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema": SCHEMA, "entries": [], "incumbents": {}}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            raise RegistryError(f"registry at {self.path} is unreadable: {e}")
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            raise RegistryError(f"registry at {self.path} is not {SCHEMA}")
        for e in doc.get("entries", []):
            try:
                c = Criterion.from_dict(e["criterion"])
            except (KeyError, TypeError, CriterionError) as exc:
                raise RegistryError(f"entry is not a criterion: {exc}")
            if c.sha256() != e.get("criterion_sha256"):
                raise RegistryError(
                    f"entry {e.get('criterion_id')} v{e.get('version')} does not "
                    "match its recorded hash: the file was edited in place")
        return doc

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")

    # --- reads ---------------------------------------------------------------

    def entries(self) -> list[dict]:
        return self._load()["entries"]

    def entry(self, criterion_id: str, version: int) -> dict | None:
        for e in self.entries():
            if e["criterion_id"] == criterion_id and e["version"] == version:
                return e
        return None

    def live(self) -> list[dict]:
        return [e for e in self.entries() if e["status"] == "live"]

    def reward_eligible_ids(self) -> list[str]:
        return sorted({e["criterion_id"] for e in self.live()
                       if e["reward_eligible"]})

    def incumbent(self, criterion_id: str) -> Incumbent | None:
        d = self._load().get("incumbents", {}).get(criterion_id)
        return Incumbent(**d) if d else None

    # --- writes --------------------------------------------------------------

    def admit(self, criterion: Criterion, *, qa_card=None) -> dict:
        doc = self._load()
        digest = criterion.sha256()
        same = [e for e in doc["entries"]
                if e["criterion_id"] == criterion.criterion_id]

        for e in same:
            if e["criterion_sha256"] == digest:
                return e                                  # idempotent
        if same and not criterion.parent_sha256:
            raise RegistryError(
                f"{criterion.criterion_id} is already registered with different "
                "content and this candidate records no parent. Use amend() so "
                "the change is visible as a change.")
        if criterion.parent_sha256:
            if not any(e["criterion_sha256"] == criterion.parent_sha256
                       for e in same):
                raise RegistryError(
                    f"parent {criterion.parent_sha256[:22]} of "
                    f"{criterion.criterion_id} v{criterion.version} is not "
                    "registered here")
            for e in same:
                if e["criterion_sha256"] == criterion.parent_sha256:
                    e["status"] = "superseded"

        # Two questions, and both must hold. The criterion answers whether this
        # SHAPE may mint a reward; the card answers whether the checker that will
        # grade it is actually sound. Asking only the first leaves an unmeasured
        # checker reward-eligible, which is the condition the QA gate exists to
        # prevent. The shape is checked first so the more fundamental refusal is
        # the one a reader sees.
        ok, reason = criterion.reward_eligible()
        if ok:
            card_family = getattr(qa_card, "family", None)
            if qa_card is None:
                ok, reason = False, "QA_CARD_ABSENT"
            elif card_family not in (None, criterion.family):
                raise RegistryError(
                    f"qa card grades family {card_family!r}, criterion is "
                    f"{criterion.family!r}: a card from another family would let "
                    "a sound checker vouch for an unmeasured one")
            elif not qa_card.passed:
                ok, reason = False, "QA_CARD_FAILED"

        entry = {
            "criterion_id": criterion.criterion_id,
            "version": criterion.version,
            "criterion_sha256": digest,
            "parent_sha256": criterion.parent_sha256,
            "change_reason": criterion.change_reason,
            "status": "live",
            "reward_eligible": ok,
            "reward_ineligible_reason": "" if ok else reason,
            # A decimal string, never a float: this lands in a hashed record and
            # cross-platform float formatting is how a stranger's replay
            # disagrees over nothing real.
            "qa_card_hash": qa_card.card_hash() if qa_card else "",
            "qa_card_passed": bool(qa_card.passed) if qa_card else False,
            "false_accept_upper_bound": (
                f"{qa_card.false_accept_upper_bound:.6f}" if qa_card else ""),
            "criterion": criterion.to_dict(),
            "invalidation": None,
        }
        doc["entries"].append(entry)
        self._save(doc)
        return entry

    def set_incumbent(self, inc: Incumbent) -> None:
        doc = self._load()
        if not any(e["criterion_id"] == inc.criterion_id
                   for e in doc["entries"]):
            raise RegistryError(
                f"no criterion {inc.criterion_id} is registered")
        if not isinstance(inc.value, str):
            raise RegistryError(
                "incumbent value must be a decimal STRING, never a float: "
                "cross-platform float formatting breaks replay")
        if inc.source in PUBLISHED_SOURCES and len(inc.citations) < CITATIONS_REQUIRED:
            raise RegistryError(
                f"a {inc.source} incumbent needs {CITATIONS_REQUIRED} independent "
                f"citations, got {len(inc.citations)}")
        doc.setdefault("incumbents", {})[inc.criterion_id] = inc.to_dict()
        self._save(doc)

    def invalidate(self, criterion_id: str, version: int,
                   code: InvalidationCode, note: str = "") -> dict:
        if not isinstance(code, InvalidationCode):
            raise RegistryError(
                "invalidation needs a typed InvalidationCode, not free text")
        doc = self._load()
        for e in doc["entries"]:
            if e["criterion_id"] == criterion_id and e["version"] == version:
                e["status"] = "invalidated"
                e["invalidation"] = {"reason_code": code.value, "note": note}
                self._save(doc)
                return e
        raise RegistryError(f"no {criterion_id} v{version} to invalidate")

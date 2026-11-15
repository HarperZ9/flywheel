from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import ClassVar

from .canonical_json import canonical_json_text

ADAPTER_SCHEMA = "canon.adapter/v1"
INTEGRATION_TIERS = ("enforced", "native-advisory", "guided", "unsupported")
_ADAPTER_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TIER_STRENGTH = {"unsupported": 0, "guided": 1, "native-advisory": 2, "enforced": 3}
_VERSION = "foundation-2026-08-30"
_EVIDENCE_REFS = (
    "project-docs/CANON-CONTINUITY-CAPSULE-DESIGN.md",
    "project-docs/APPROVAL-CANON-CONTINUITY-20260830.md",
)
_RETIREMENT_TRIGGER = "Revise when blocking startup proof fixtures or host capability evidence change."
_BUILTIN_SPECS = (
    ("codex-cli", "Codex CLI", "native-advisory", ("CANON.md", "AGENTS.md"), ("file", "paste"), ("file", "stdout"), "native-context-file", "Native context can advise the run; this foundation descriptor does not assert a universal hard block before work."),
    ("claude-code", "Claude Code", "native-advisory", ("CANON.md", "CLAUDE.md"), ("file", "paste"), ("file", "stdout"), "native-context-file", "Native context can advise the run; this foundation descriptor does not assert a universal hard block before work."),
    ("chatgpt-app", "ChatGPT App", "guided", ("CANON.md", "chat-message"), ("paste", "file"), ("chat", "file"), "guided-user-message", "Closed app bootstrap is guided until blocking startup fixtures prove promotion."),
    ("claude-app", "Claude App", "guided", ("CANON.md", "chat-message"), ("paste", "file"), ("chat", "file"), "guided-user-message", "Closed app bootstrap is guided until blocking startup fixtures prove promotion."),
    ("api-runner", "API Runner", "guided", ("CANON.md", "json"), ("file", "json"), ("json", "stdout"), "caller-managed", "API runner enforcement depends on caller wiring and remains guided until blocking fixtures prove promotion."),
    ("local-runner", "Local Runner", "guided", ("CANON.md", "json"), ("file", "json"), ("json", "stdout"), "caller-managed", "Local runner enforcement depends on harness wiring and remains guided until blocking fixtures prove promotion."),
    ("mcp-readonly", "MCP Readonly", "guided", ("CANON.md", "mcp-resource"), ("file", "resource"), ("resource", "stdout"), "readonly-resource-handoff", "MCP read-only resources can expose context; this foundation descriptor does not assert tool-call blocking before work."),
    ("a2a-artifact", "A2A Artifact", "guided", ("CANON.md", "artifact"), ("file", "artifact"), ("artifact", "stdout"), "artifact-handoff", "Artifact handoff can carry context; this foundation descriptor does not assert host-level blocking before work."),
)


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    adapter_id: str
    display_name: str
    version: str
    integration_tier: str
    target_surfaces: tuple[str, ...]
    import_modes: tuple[str, ...]
    export_modes: tuple[str, ...]
    bootstrap: dict
    losses: tuple[dict, ...] = ()
    limits: dict = field(default_factory=dict)
    auth: dict = field(default_factory=dict)
    privacy: dict = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    known_unknowns: tuple[str, ...] = ()
    last_verified: str | None = None
    owner: str | None = None
    retirement_trigger: str | None = None

    schema: ClassVar[str] = ADAPTER_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_surfaces", _tuple_sequence(self.target_surfaces))
        object.__setattr__(self, "import_modes", _tuple_sequence(self.import_modes))
        object.__setattr__(self, "export_modes", _tuple_sequence(self.export_modes))
        object.__setattr__(self, "bootstrap", copy.deepcopy(self.bootstrap))
        object.__setattr__(self, "losses", _tuple_sequence(self.losses))
        object.__setattr__(self, "limits", copy.deepcopy(self.limits))
        object.__setattr__(self, "auth", copy.deepcopy(self.auth))
        object.__setattr__(self, "privacy", copy.deepcopy(self.privacy))
        object.__setattr__(self, "evidence_refs", _tuple_sequence(self.evidence_refs))
        object.__setattr__(self, "known_unknowns", _tuple_sequence(self.known_unknowns))

    def to_dict(self) -> dict:
        return {
            "schema": ADAPTER_SCHEMA,
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "version": self.version,
            "integration_tier": self.integration_tier,
            "target_surfaces": _json_sequence(self.target_surfaces),
            "import_modes": _json_sequence(self.import_modes),
            "export_modes": _json_sequence(self.export_modes),
            "bootstrap": copy.deepcopy(self.bootstrap),
            "losses": _json_sequence(self.losses),
            "limits": copy.deepcopy(self.limits),
            "auth": copy.deepcopy(self.auth),
            "privacy": copy.deepcopy(self.privacy),
            "evidence_refs": _json_sequence(self.evidence_refs),
            "known_unknowns": _json_sequence(self.known_unknowns),
            "last_verified": self.last_verified,
            "owner": self.owner,
            "retirement_trigger": self.retirement_trigger,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AdapterDescriptor":
        if not isinstance(d, dict):
            raise TypeError(f"adapter descriptor JSON must be an object, got {type(d).__name__}")
        got = d.get("schema")
        if got != ADAPTER_SCHEMA:
            raise ValueError(f"expected schema {ADAPTER_SCHEMA!r}, got {got!r}")
        return cls(
            adapter_id=d["adapter_id"],
            display_name=d["display_name"],
            version=d["version"],
            integration_tier=d["integration_tier"],
            target_surfaces=d["target_surfaces"],
            import_modes=d["import_modes"],
            export_modes=d["export_modes"],
            bootstrap=d["bootstrap"],
            losses=d.get("losses", ()),
            limits=d.get("limits", {}),
            auth=d.get("auth", {}),
            privacy=d.get("privacy", {}),
            evidence_refs=d.get("evidence_refs", ()),
            known_unknowns=d.get("known_unknowns", ()),
            last_verified=d.get("last_verified"),
            owner=d.get("owner"),
            retirement_trigger=d.get("retirement_trigger"),
        )

    def to_json(self) -> str:
        return canonical_json_text(self.to_dict())


def builtin_descriptors() -> tuple[AdapterDescriptor, ...]:
    return tuple(_builtin_descriptor(*spec) for spec in _BUILTIN_SPECS)


def descriptor_for(adapter_id: str) -> AdapterDescriptor:
    for descriptor in builtin_descriptors():
        if descriptor.adapter_id == adapter_id:
            return descriptor
    raise KeyError(adapter_id)


def assert_requested_tier_allowed(desc: AdapterDescriptor, requested_tier: str) -> None:
    if requested_tier not in _TIER_STRENGTH:
        raise ValueError(f"unknown tier: {requested_tier!r}")
    declared = _TIER_STRENGTH.get(desc.integration_tier)
    if declared is None:
        raise ValueError(f"descriptor declares unknown tier: {desc.integration_tier!r}")
    if _TIER_STRENGTH[requested_tier] > declared:
        raise ValueError(
            f"requested tier {requested_tier!r} is stronger than descriptor tier {desc.integration_tier!r}"
        )


def validate_adapter_descriptor(adapter: AdapterDescriptor) -> list[str]:
    if not isinstance(adapter, AdapterDescriptor):
        return ["adapter descriptor must be an AdapterDescriptor"]
    problems: list[str] = []
    _check_adapter_id(adapter.adapter_id, problems)
    _check_non_empty_string("display_name", adapter.display_name, problems)
    _check_non_empty_string("version", adapter.version, problems)
    _check_member("integration_tier", adapter.integration_tier, INTEGRATION_TIERS, problems)
    _check_string_tuple("target_surfaces", adapter.target_surfaces, problems, required=True)
    _check_string_tuple("import_modes", adapter.import_modes, problems, required=True)
    _check_string_tuple("export_modes", adapter.export_modes, problems, required=True)
    _check_dict("bootstrap", adapter.bootstrap, problems)
    _check_dict_tuple("losses", adapter.losses, problems)
    _check_dict("limits", adapter.limits, problems)
    _check_dict("auth", adapter.auth, problems)
    _check_dict("privacy", adapter.privacy, problems)
    _check_string_tuple("evidence_refs", adapter.evidence_refs, problems)
    _check_string_tuple("known_unknowns", adapter.known_unknowns, problems)
    _check_optional_string("last_verified", adapter.last_verified, problems)
    _check_optional_string("owner", adapter.owner, problems)
    _check_optional_string("retirement_trigger", adapter.retirement_trigger, problems)
    _check_bootstrap_contract(adapter, problems)
    _check_enforced_evidence(adapter, problems)
    return problems


def _builtin_descriptor(
    adapter_id: str,
    display_name: str,
    integration_tier: str,
    target_surfaces: tuple[str, ...],
    import_modes: tuple[str, ...],
    export_modes: tuple[str, ...],
    mode: str,
    known_unknown: str,
) -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id=adapter_id,
        display_name=display_name,
        version=_VERSION,
        integration_tier=integration_tier,
        target_surfaces=target_surfaces,
        import_modes=import_modes,
        export_modes=export_modes,
        bootstrap={"can_block_before_work": False, "mode": mode},
        losses=(),
        limits={"max_context_tokens": None},
        auth={"requires_login": False},
        privacy={"default_disclosure": "project-only"},
        evidence_refs=_EVIDENCE_REFS,
        known_unknowns=(known_unknown,),
        last_verified="2026-08-30",
        owner="canon",
        retirement_trigger=_RETIREMENT_TRIGGER,
    )


def _tuple_sequence(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return tuple(copy.deepcopy(item) for item in value)
    return copy.deepcopy(value)


def _json_sequence(value: object) -> object:
    if isinstance(value, tuple):
        return [copy.deepcopy(item) for item in value]
    if isinstance(value, list):
        return [copy.deepcopy(item) for item in value]
    return copy.deepcopy(value)


def _check_adapter_id(value: object, problems: list[str]) -> None:
    if not isinstance(value, str) or _ADAPTER_ID_RE.fullmatch(value) is None:
        problems.append("adapter_id must be lowercase ASCII words separated by hyphens")


def _check_non_empty_string(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, str) or value == "":
        problems.append(f"{name} must be a non-empty string")


def _check_optional_string(name: str, value: object, problems: list[str]) -> None:
    if value is not None and not isinstance(value, str):
        problems.append(f"{name} must be a string or None")


def _check_member(name: str, value: object, allowed: tuple[str, ...], problems: list[str]) -> None:
    if value not in allowed:
        problems.append(f"{name} must be one of {list(allowed)}, got {value!r}")


def _check_string_tuple(name: str, value: object, problems: list[str], required: bool = False) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    if required and not value:
        problems.append(f"{name} must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            problems.append(f"{name}[{index}] must be a string")


def _check_dict_tuple(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            problems.append(f"{name}[{index}] must be a dict")


def _check_dict(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append(f"{name} must be a dict")


def _check_bootstrap_contract(adapter: AdapterDescriptor, problems: list[str]) -> None:
    if not isinstance(adapter.bootstrap, dict):
        return
    blocking = adapter.bootstrap.get("can_block_before_work")
    if not isinstance(blocking, bool):
        problems.append("bootstrap.can_block_before_work must be bool")
    mode = adapter.bootstrap.get("mode")
    if mode is not None and (not isinstance(mode, str) or mode == ""):
        problems.append("bootstrap.mode must be a non-empty string when present")


def _check_enforced_evidence(adapter: AdapterDescriptor, problems: list[str]) -> None:
    if adapter.integration_tier != "enforced":
        return
    can_block = isinstance(adapter.bootstrap, dict) and adapter.bootstrap.get("can_block_before_work") is True
    has_evidence = isinstance(adapter.evidence_refs, tuple) and len(adapter.evidence_refs) > 0
    if not can_block or not has_evidence:
        problems.append("enforced adapters require blocking bootstrap evidence and at least one evidence_ref")

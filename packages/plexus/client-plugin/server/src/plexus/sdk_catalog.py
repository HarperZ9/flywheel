"""Compact model-native tool and capability registry across all 5 flagships + Colab."""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Any, Sequence

CATALOG_SCHEMA = "flagship-agent-sdk-catalog/1"

_TYPE_CHECKERS: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "float": (int, float),
    "bool": (bool,),
    "dict": (dict,),
    "list": (list,),
}

_JSON_TYPES: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "dict": "object",
    "list": "array",
}


@dataclass(frozen=True)
class AgentToolSpec:
    """Compact typed descriptor for one cross-flagship model-native tool."""

    name: str
    flagship: str
    summary: str
    required_args: dict[str, str]
    optional_args: dict[str, str]
    output_invariants: tuple[str, ...]
    next_valid_actions: tuple[str, ...]
    mutates: bool = False
    destructive: bool = False

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "flagship": self.flagship,
            "summary": self.summary,
            "req": dict(self.required_args),
            "opt": dict(self.optional_args),
            "inv": list(self.output_invariants),
            "next": list(self.next_valid_actions),
            "mut": self.mutates,
            "destr": self.destructive,
        }

    def to_json_schema(self) -> dict[str, Any]:
        props: dict[str, dict[str, str]] = {}
        for k, t in {**self.required_args, **self.optional_args}.items():
            props[k] = {"type": _JSON_TYPES.get(t, "string")}
        return {"type": "object", "properties": props, "required": list(self.required_args)}


BUILTIN_SDK_TOOLS: tuple[AgentToolSpec, ...] = (
    AgentToolSpec(
        "cmmns.ingest_sidecar", "cmmns", "Parse daylight.sidecar/1 post into deduped claims and targets.",
        {"path": "str"}, {"dedup": "bool"}, ("sha256_id", "deduped"), ("gather.deconstruct",),
    ),
    AgentToolSpec(
        "gather.deconstruct", "gather", "Deconstruct paper, audio, video, image, or sidecar into manifest.",
        {"path": "str"}, {"out_dir": "str", "workflow": "str"}, ("media-deconstruction/1", "engine-receipt/1"),
        ("superframe.synthesize_material", "flywheel.verify_three_plate"), mutates=True,
    ),
    AgentToolSpec(
        "superframe.synthesize_material", "superframe", "Synthesize spectral 380-780nm tileable material and shader.",
        {"material_id": "str"}, {"illuminant": "str", "shader": "str"}, ("edge_delta==0", "0<=R<=1"),
        ("superframe.forge_meshlet_glb", "flywheel.verify_three_plate"),
    ),
    AgentToolSpec(
        "superframe.forge_meshlet_glb", "superframe", "Forge procedural mesh/flora packed into 64v/126t GLB meshlets.",
        {"kind": "str", "seed": "int"}, {"season": "str"}, ("<=64v/126t", "glb_v2"),
        ("superframe.step_physai", "flywheel.verify_three_plate"), mutates=True,
    ),
    AgentToolSpec(
        "superframe.step_physai", "superframe", "Run SI rigid-body PGS/Coulomb physics environment rollout.",
        {"env": "str", "seed": "int"}, {"steps": "int", "gravity": "float"}, ("coulomb_cone", "replay_sha256"),
        ("colab.emit_stage1_job_spec", "flywheel.verify_three_plate"),
    ),
    AgentToolSpec(
        "superframe.run_noh1", "superframe", "Run 4-level Nested Organism Hierarchy evaluation episode.",
        {"seed": "int"}, {"generations": "int"}, ("immune_zero_fa", "replay_sha256"),
        ("flywheel.verify_three_plate",),
    ),
    AgentToolSpec(
        "buildlang.compile_and_check", "buildlang", "Typecheck and compile a BuildLang .bld source with buildc.",
        {"source_path": "str"}, {"optimize": "bool"}, ("exit_code==0", "0_warnings"),
        ("buildlang.eval_kernel", "flywheel.verify_three_plate"),
    ),
    AgentToolSpec(
        "buildlang.eval_kernel", "buildlang", "Evaluate a deterministic BuildLang physics or AI kernel.",
        {"kernel": "str", "inputs": "dict"}, {"threads": "int"}, ("bit_exact", "fnv1a_digest"),
        ("flywheel.verify_three_plate",),
    ),
    AgentToolSpec(
        "flywheel.verify_three_plate", "flywheel", "Verify candidate via Plate A/B/C Three-Plate oracle.",
        {"artifact_path": "str"}, {"strict": "bool"}, ("plate_abc", "verdict"),
        ("flywheel.run_operator_plan", "site.verify_surface"),
    ),
    AgentToolSpec(
        "flywheel.run_operator_plan", "flywheel", "Run authority-gated workstation operator plan with rollback.",
        {"actions": "list"}, {"allowed_root": "str", "destructive": "bool"}, ("journal_chain", "rollback_safe"),
        ("flywheel.verify_three_plate",), mutates=True, destructive=True,
    ),
    AgentToolSpec(
        "colab.emit_stage1_job_spec", "colab", "Emit budget-capped Colab Pro+ job spec with data-gate check.",
        {"job_id": "str", "profile": "str"},
        {"accelerator": "str", "compute_unit_cap": "float", "data_gate_passed": "bool"},
        ("colab-job/1", "data_gate"), ("flywheel.verify_three_plate",),
    ),
    AgentToolSpec(
        "site.verify_surface", "site", "Verify portfolio static surface links, metadata, and prose hygiene.",
        {"target_page": "str"}, {"check_links": "bool"}, ("em_dash==0", "0_broken_links"),
        ("flywheel.verify_three_plate",),
    ),
)

TOOL_INDEX: dict[str, AgentToolSpec] = {spec.name: spec for spec in BUILTIN_SDK_TOOLS}


def estimate_tokens(obj: Any) -> int:
    """Conservative deterministic token estimate for a compact JSON tool descriptor."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return max(1, (len(raw) + 3) // 4)


def _format_tool_entry(spec: AgentToolSpec, fmt: str) -> dict[str, Any]:
    if fmt == "compact":
        return spec.to_compact_dict()
    if fmt == "openai":
        return {
            "type": "function",
            "function": {"name": spec.name, "description": spec.summary, "parameters": spec.to_json_schema()},
        }
    if fmt == "mcp":
        return {
            "name": spec.name,
            "description": spec.summary,
            "inputSchema": spec.to_json_schema(),
            "flagship": spec.flagship,
        }
    raise ValueError(f"unsupported catalog format: {fmt}")


def export_compact_catalog(
    max_tokens_per_tool: int = 125,
    *,
    fmt: str = "compact",
    tools: Sequence[AgentToolSpec] | None = None,
) -> dict[str, Any]:
    """Export model-native tool descriptors enforcing a strict per-tool token budget."""
    selected = tuple(tools) if tools is not None else BUILTIN_SDK_TOOLS
    entries: list[dict[str, Any]] = []
    token_counts: dict[str, int] = {}
    for spec in selected:
        item = _format_tool_entry(spec, fmt)
        toks = estimate_tokens(item)
        if toks > max_tokens_per_tool:
            raise ValueError(f"tool {spec.name} exceeds token budget ({toks} > {max_tokens_per_tool})")
        entries.append(item)
        token_counts[spec.name] = toks
    return {
        "schema": CATALOG_SCHEMA,
        "format": fmt,
        "max_tokens_per_tool": max_tokens_per_tool,
        "tool_count": len(entries),
        "token_estimates": token_counts,
        "tools": entries,
    }


def _matches_type(value: Any, expected: str) -> bool:
    if expected in ("int", "float") and isinstance(value, bool):
        return False
    allowed = _TYPE_CHECKERS.get(expected)
    return True if allowed is None else isinstance(value, allowed)


def validate_tool_args(spec: AgentToolSpec, args: Any) -> list[str]:
    """Validate required and optional argument types for an AgentToolSpec."""
    if not isinstance(args, dict):
        return ["args must be a JSON object (dict)"]
    errors: list[str] = []
    for key, expected in spec.required_args.items():
        if key not in args or args[key] is None:
            errors.append(f"missing required arg '{key}' ({expected})")
        elif not _matches_type(args[key], expected):
            errors.append(f"wrong type for '{key}': expected {expected}, got {type(args[key]).__name__}")
    for key, expected in spec.optional_args.items():
        if key in args and args[key] is not None and not _matches_type(args[key], expected):
            errors.append(f"wrong type for '{key}': expected {expected}, got {type(args[key]).__name__}")
    known = set(spec.required_args) | set(spec.optional_args)
    unknown = sorted(set(args) - known)
    if unknown:
        errors.append(f"unexpected argument(s): {', '.join(unknown)}")
    return errors


def suggest_similar_tools(
    unknown_name: str,
    known_names: Sequence[str] | None = None,
    *,
    limit: int = 3,
) -> list[str]:
    """Suggest closest valid tool names for model self-correction on typos."""
    pool = list(known_names) if known_names is not None else [s.name for s in BUILTIN_SDK_TOOLS]
    matches = difflib.get_close_matches(unknown_name, pool, n=limit, cutoff=0.35)
    if matches:
        return matches
    prefix = unknown_name.split(".", 1)[0].lower()
    same_flagship = [n for n in pool if n.lower().startswith(prefix)]
    return same_flagship[:limit] if same_flagship else pool[:limit]

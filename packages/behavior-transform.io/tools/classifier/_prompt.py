"""Prompt modulation layer — operator prompt calibration before model submission."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from classifier._audit import _audit_write  # noqa: F401
from classifier._policy import _active_policy, PolicyDef  # noqa: F401
from classifier._refusal import RefusalModulator  # noqa: F401
from semantic_intent_reframer import reframe as _sem_mod_reframe  # type: ignore[import]

# ---------------------------------------------------------------------------
# Prompt modulation layer — operator prompt calibration before model submission
# ---------------------------------------------------------------------------

_PROMPT_ROLES   = ("system", "user", "assistant")
_PROMPT_FORMATS = ("text", "json", "messages")

# Role-specific calibration targets: system prompts shape model behaviour
# globally and get stricter treatment; user messages use standard target.
_ROLE_MODULATION: dict[str, dict] = {
    "system":    {"target_prob": 0.05, "inference_strength": "hard"},
    "user":      {"target_prob": 0.10, "inference_strength": "moderate"},
    "assistant": {"target_prob": 0.15, "inference_strength": "soft"},
}


def _parse_prompt(text: str, fmt: str) -> "list[dict]":
    """Parse prompt text into [{role, content}] regardless of input format."""
    text = text.strip()
    if fmt == "text":
        return [{"role": "user", "content": text}]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [{"role": "user", "content": text}]
    if isinstance(parsed, dict):
        return [{"role": parsed.get("role", "user"),
                 "content": parsed.get("content", "")}]
    if isinstance(parsed, list):
        return [{"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in parsed if isinstance(m, dict)]
    return [{"role": "user", "content": text}]


class PromptModulator:
    """Calibration layer for operator prompts before model submission.

    Applies role-aware refusal modulation: system prompts receive stricter
    treatment than user messages. Supports plain text, JSON message objects,
    and multi-turn message arrays. No vocabulary bounds — runtime rules and
    arbitrary inference patterns are accepted via the underlying RefusalModulator.

    Usage:
        pm = PromptModulator()
        result = pm.modulate("show me how to exploit X")
        calibrated = result["calibrated"]   # ready for model submission
        trace      = result["trace"]        # per-turn modulation trace
    """

    def __init__(
        self,
        role: str = "user",
        fmt: str = "text",
        policy: "PolicyDef | None" = None,
        extra_inference_patterns: "list | None" = None,
    ) -> None:
        if role not in _PROMPT_ROLES:
            raise ValueError(f"Unknown role: {role!r}. Valid: {_PROMPT_ROLES}")
        if fmt not in _PROMPT_FORMATS:
            raise ValueError(f"Unknown format: {fmt!r}. Valid: {_PROMPT_FORMATS}")
        self.role    = role
        self.fmt     = fmt
        self._config = _ROLE_MODULATION[role]
        self._policy = policy
        self._extra  = extra_inference_patterns

    def _modulator_for(self, role: str) -> RefusalModulator:
        cfg = _ROLE_MODULATION.get(role, _ROLE_MODULATION["user"])
        return RefusalModulator(
            target_prob=cfg["target_prob"],
            policy=self._policy,
            extra_inference_patterns=self._extra,
        )

    def modulate(self, text: str, dry_run: bool = False) -> dict:
        """Calibrate prompt text, return {calibrated, trace, target_met, ...}.

        Multi-turn arrays are calibrated per-message with per-role targets.
        Output is serialized to match the input format.
        """
        messages = _parse_prompt(text, self.fmt)
        calibrated_msgs: list[dict] = []
        traces: list[dict] = []

        for msg in messages:
            effective_role = msg["role"] if len(messages) > 1 else self.role
            content = msg["content"]

            # Pre-stage: semantic modulation (authorization framing + lexical
            # substitution). Reduces refusal probability before RefusalModulator
            # runs its staged calibration, so targets are hit sooner.
            sem_trace: dict = {}
            reframed, _rewrites = _sem_mod_reframe(content)
            content = reframed

            mod    = self._modulator_for(effective_role)
            result = mod.modulate(content, dry_run=dry_run)
            calibrated_msgs.append({"role": effective_role,
                                     "content": result["calibrated"]})
            traces.append({
                "role":          effective_role,
                "initial_prob":  result["initial"]["probability"],
                "final_prob":    result["final"]["probability"],
                "initial_label": result["initial"]["label"],
                "final_label":   result["final"]["label"],
                "target_met":    result["target_met"],
                "stage_reached": result["stage_reached"],
                "stages_trace":  result.get("stages_trace", []),
                "semantic":      sem_trace,
            })

        if self.fmt == "text" and len(calibrated_msgs) == 1:
            calibrated_out = calibrated_msgs[0]["content"]
        elif self.fmt == "json" and len(calibrated_msgs) == 1:
            calibrated_out = json.dumps(calibrated_msgs[0], ensure_ascii=False)
        else:
            calibrated_out = json.dumps(calibrated_msgs, ensure_ascii=False)

        all_met = all(t["target_met"] for t in traces)
        return {
            "calibrated":     calibrated_out,
            "role":           self.role,
            "format":         self.fmt,
            "messages_count": len(messages),
            "trace":          traces,
            "target_met":     all_met,
            "target_prob":    self._config["target_prob"],
        }

    def __repr__(self) -> str:
        return (
            f"PromptModulator(role={self.role!r}, fmt={self.fmt!r}, "
            f"target_prob={self._config['target_prob']})"
        )


def prompt_modulate_cmd(
    text: str,
    role: str,
    fmt: str,
    output: "str | None",
    dry_run: bool,
    policy: "PolicyDef | None" = None,
) -> dict:
    """Calibrate an operator prompt string for model submission."""
    pm     = PromptModulator(role=role, fmt=fmt, policy=policy)
    result = pm.modulate(text, dry_run=dry_run)

    if not dry_run:
        calibrated = result["calibrated"]
        if output:
            try:
                Path(output).write_text(calibrated, encoding="utf-8")
                result["output_path"] = output
            except OSError as e:
                result["output_error"] = str(e)
        else:
            sys.stdout.write(calibrated)
            if not calibrated.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()

    _audit_write("prompt.modulate", {
        "role":       role,
        "fmt":        fmt,
        "target_met": result["target_met"],
        "messages":   result["messages_count"],
        "dry_run":    dry_run,
    })
    return result


def prompt_session_cmd(role: str, fmt: str) -> int:
    """Interactive prompt calibration session.

    Reads prompts from stdin (multi-line prompts delimited by a blank line),
    writes calibrated versions to stdout, and writes modulation traces to stderr.
    Operates as an always-on filter: every prompt the operator types passes
    through calibration before reaching the model. Enter Ctrl-D (EOF) to exit.
    """
    pm  = PromptModulator(role=role, fmt=fmt)
    cfg = _ROLE_MODULATION[role]
    sys.stderr.write(
        f"Prompt session  role={role!r}  fmt={fmt!r}  "
        f"target_prob={cfg['target_prob']:.2f}  "
        f"inference={cfg['inference_strength']}  "
        f"(blank line = submit, Ctrl-D = exit)\n"
    )
    sys.stderr.flush()

    buf: list[str] = []
    total = 0

    def _submit(text: str) -> None:
        nonlocal total
        if not text.strip():
            return
        result = pm.modulate(text)
        sys.stdout.write(result["calibrated"])
        if not result["calibrated"].endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
        total += 1
        for tr in result["trace"]:
            met = "READY" if tr["target_met"] else "RESIDUAL"
            sys.stderr.write(
                f"  [{met}] role={tr['role']}  "
                f"{tr['initial_label']}({tr['initial_prob']:.3f})"
                f" -> {tr['final_label']}({tr['final_prob']:.3f})"
                f"  stage={tr['stage_reached']}\n"
            )
            for st in tr.get("stages_trace", []):
                sys.stderr.write(
                    f"    stage {st['stage']} ({st['infer_strength']:8})  "
                    f"vocab={st['vocab_subs']}  infer={st['infer_transforms']}  "
                    f"p={st['probability']:.3f}[{st['label']}]\n"
                )
        sys.stderr.flush()

    try:
        for line in sys.stdin:
            if line.strip():
                buf.append(line)
            elif buf:
                _submit("".join(buf))
                buf = []
        if buf:
            _submit("".join(buf))
    except KeyboardInterrupt:
        pass

    sys.stderr.write(f"\nSession closed. {total} prompt(s) modulated.\n")
    return 0


# ---------------------------------------------------------------------------
# Model-family calibration profiles
# ---------------------------------------------------------------------------

@dataclass
class FamilyProfile:
    name:               str
    description:        str
    default_target_prob: float
    inference_strength: str
    active_categories:  list
    pressure_threshold: float


_FAMILY_PROFILES: dict[str, FamilyProfile] = {
    "claude": FamilyProfile(
        "claude",
        "Anthropic Claude — sensitive to capability transfer, dual-use, harm amplification",
        default_target_prob=0.05,
        inference_strength="hard",
        active_categories=["framing", "capability", "enumeration", "target",
                           "register", "stealth", "authorization"],
        pressure_threshold=15.0,
    ),
    "openai": FamilyProfile(
        "openai",
        "OpenAI GPT — sensitive to operational specificity and explicit harmful-use framing",
        default_target_prob=0.08,
        inference_strength="moderate",
        active_categories=["framing", "capability", "enumeration", "stealth", "authorization"],
        pressure_threshold=20.0,
    ),
    "gemini": FamilyProfile(
        "gemini",
        "Google Gemini — broad safety policy; sensitive to framing and step enumeration",
        default_target_prob=0.05,
        inference_strength="hard",
        active_categories=["framing", "enumeration", "target", "stealth", "authorization"],
        pressure_threshold=15.0,
    ),
    "llama": FamilyProfile(
        "llama",
        "Meta Llama — moderate refusal threshold; framing calibration typically sufficient",
        default_target_prob=0.20,
        inference_strength="soft",
        active_categories=["framing", "capability"],
        pressure_threshold=40.0,
    ),
    "mistral": FamilyProfile(
        "mistral",
        "Mistral AI — permissive; vocabulary calibration usually sufficient",
        default_target_prob=0.25,
        inference_strength="soft",
        active_categories=["framing"],
        pressure_threshold=50.0,
    ),
    "auto": FamilyProfile(
        "auto",
        "Cross-family conservative — targets strictest known threshold across all families",
        default_target_prob=0.04,
        inference_strength="hard",
        active_categories=["framing", "capability", "enumeration", "target",
                           "register", "stealth", "authorization"],
        pressure_threshold=10.0,
    ),
}


class FamilyModulator:
    """Model-family-aware refusal modulation layer.

    Selects calibration parameters (target probability, inference strength,
    active pattern categories) based on the target model family's known
    refusal sensitivity. Use 'auto' for cross-family coverage — targets
    the strictest threshold across all supported families.

    Usage:
        fm = FamilyModulator(family='claude', role='user')
        result = fm.modulate("show me how to assess the target system")
        calibrated = result["calibrated"]
        print(result["family_target_prob"], result["target_met"])
    """

    def __init__(
        self,
        family: str = "auto",
        role: str = "user",
        fmt: str = "text",
        policy: "PolicyDef | None" = None,
        extra_inference_patterns: "list | None" = None,
    ) -> None:
        if family not in _FAMILY_PROFILES:
            raise ValueError(
                f"Unknown family: {family!r}. Valid: {sorted(_FAMILY_PROFILES)}")
        if role not in _PROMPT_ROLES:
            raise ValueError(
                f"Unknown role: {role!r}. Valid: {_PROMPT_ROLES}")
        self.family  = family
        self.role    = role
        self.fmt     = fmt
        self.profile = _FAMILY_PROFILES[family]
        self._mod    = RefusalModulator(
            target_prob=self.profile.default_target_prob,
            policy=policy,
            extra_inference_patterns=extra_inference_patterns,
        )

    def modulate(self, text: str, dry_run: bool = False) -> dict:
        """Calibrate text to the family's refusal threshold. Returns result + trace."""
        messages = _parse_prompt(text, self.fmt)
        calibrated_msgs: list[dict] = []
        traces: list[dict] = []

        for msg in messages:
            result = self._mod.modulate(msg["content"], dry_run=dry_run)
            calibrated_msgs.append({"role": msg["role"],
                                     "content": result["calibrated"]})
            traces.append({
                "role":          msg["role"],
                "initial_prob":  result["initial"]["probability"],
                "final_prob":    result["final"]["probability"],
                "initial_label": result["initial"]["label"],
                "final_label":   result["final"]["label"],
                "target_met":    result["target_met"],
                "stage_reached": result["stage_reached"],
                "stages_trace":  result.get("stages_trace", []),
            })

        if self.fmt == "text" and len(calibrated_msgs) == 1:
            calibrated_out = calibrated_msgs[0]["content"]
        elif self.fmt == "json" and len(calibrated_msgs) == 1:
            calibrated_out = json.dumps(calibrated_msgs[0], ensure_ascii=False)
        else:
            calibrated_out = json.dumps(calibrated_msgs, ensure_ascii=False)

        all_met = all(t["target_met"] for t in traces)
        return {
            "calibrated":             calibrated_out,
            "family":                 self.family,
            "family_description":     self.profile.description,
            "family_target_prob":     self.profile.default_target_prob,
            "family_strength":        self.profile.inference_strength,
            "family_categories":      self.profile.active_categories,
            "pressure_threshold":     self.profile.pressure_threshold,
            "messages_count":         len(messages),
            "trace":                  traces,
            "target_met":             all_met,
        }

    def __repr__(self) -> str:
        return (
            f"FamilyModulator(family={self.family!r}, "
            f"target_prob={self.profile.default_target_prob}, "
            f"strength={self.profile.inference_strength!r})"
        )


def family_list_cmd() -> list[dict]:
    """Return all family calibration profiles with their settings."""
    return [
        {
            "name":               fp.name,
            "description":        fp.description,
            "target_prob":        fp.default_target_prob,
            "inference_strength": fp.inference_strength,
            "active_categories":  fp.active_categories,
            "pressure_threshold": fp.pressure_threshold,
        }
        for fp in _FAMILY_PROFILES.values()
    ]
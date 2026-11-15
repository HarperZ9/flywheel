"""Full-stack semantic transform — single entry point for all layers.

Chains every subsystem into one coherent pass:
  1. Category detection (14 categories, 4 tiers)
  2. Vocabulary substitution (150+ rules)
  3. Semantic modulation (5-layer general)
  4. Cyber modulation (12 ATT&CK phases, technique mapping)
  5. Prose calibration (multilingual)
  6. Compound reframing
  7. Authorization framing injection
  8. Token optimization (optional)

The result carries provenance for every transformation applied, making
the full chain auditable and reversible where applicable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from modulation_context import generate_request_id, set_request_id, set_detection_result


@dataclass
class TransformLayer:
    """Record of one transformation layer's contribution."""
    name: str
    applied: bool
    detail: str = ""
    count: int = 0


@dataclass
class TransformResult:
    """Complete result of a full-stack transform."""
    original: str
    transformed: str
    mode: str
    layers: list[TransformLayer] = field(default_factory=list)
    framing: str = ""
    blocked: bool = False
    block_reason: str = ""

    @property
    def changed(self) -> bool:
        return self.transformed != self.original

    @property
    def layer_count(self) -> int:
        return sum(1 for layer in self.layers if layer.applied)

    @property
    def total_substitutions(self) -> int:
        return sum(layer.count for layer in self.layers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "transformed": self.transformed,
            "mode": self.mode,
            "changed": self.changed,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "framing": self.framing,
            "layer_count": self.layer_count,
            "total_substitutions": self.total_substitutions,
            "layers": [
                {"name": l.name, "applied": l.applied,
                 "detail": l.detail, "count": l.count}
                for l in self.layers
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        lines = [f"Transform ({self.mode}):"]
        if self.blocked:
            lines.append(f"  BLOCKED: {self.block_reason}")
            return "\n".join(lines)
        lines.append(f"  Changed: {self.changed}")
        lines.append(f"  Layers active: {self.layer_count}/{len(self.layers)}")
        lines.append(f"  Total substitutions: {self.total_substitutions}")
        for layer in self.layers:
            mark = "+" if layer.applied else "-"
            detail = f" ({layer.detail})" if layer.detail else ""
            lines.append(f"  [{mark}] {layer.name}{detail}")
        if self.framing:
            lines.append(f"  Framing: {len(self.framing)} chars injected")
        return "\n".join(lines)


def transform_text(
    text: str,
    *,
    mode: str = "full",
    include_framing: bool = True,
    optimize: bool = False,
) -> TransformResult:
    """Run text through the full semantic transform stack.

    Args:
        text: input text to transform
        mode: "full" (all layers), "cyber" (cyber-focused), "prose" (calibration only)
        include_framing: inject authorization framing context
        optimize: run token optimization on the result
    """
    layers: list[TransformLayer] = []
    working = text
    framing = ""
    request_id = generate_request_id()
    set_request_id(request_id)

    heatmap = None
    try:
        from surface_heatmap import SurfaceHeatmap
        heatmap = SurfaceHeatmap()
    except Exception:
        pass

    # Layer 0: Obfuscation normalization (always runs first)
    try:
        from adaptive_modulator import normalize_obfuscation
        normalized, obf_count = normalize_obfuscation(working)
        layers.append(TransformLayer(
            name="obfuscation_normalization",
            applied=obf_count > 0,
            detail=f"{obf_count} normalizations" if obf_count else "clean",
            count=obf_count,
        ))
        if obf_count > 0:
            working = normalized
    except Exception as e:
        layers.append(TransformLayer(name="obfuscation_normalization", applied=False, detail=str(e)))

    # Layer 1: Category detection
    try:
        from categories import category_detector
        detector = category_detector()
        detection = detector.detect(working)
        detected_count = sum(1 for d in detection.detections if d.detected)
        layers.append(TransformLayer(
            name="categories",
            applied=detected_count > 0,
            detail=f"{detected_count} categories detected",
            count=detected_count,
        ))
        set_detection_result(detection)
        if heatmap and detection.required_rewrite:
            for d in detection.detections:
                if d.detected:
                    heatmap.record_observation(d.category.value, d.severity, "transform")
        try:
            from response_demodulator import register_modulation_for_request
            register_modulation_for_request(request_id, detection)
        except Exception:
            pass
        if detection.required_rewrite:
            working = detection.rewritten
    except Exception as e:
        layers.append(TransformLayer(name="categories", applied=False, detail=str(e)))

    # Layer 2: Vocabulary substitution
    if mode in ("full", "cyber"):
        try:
            from vocabulary_substitutions import apply_substitutions
            sub_result = apply_substitutions(working)
            applied = len(sub_result.applied_rules)
            layers.append(TransformLayer(
                name="vocabulary_substitutions",
                applied=applied > 0,
                detail=f"{applied} rules applied",
                count=applied,
            ))
            if applied > 0:
                working = sub_result.substituted
        except Exception as e:
            layers.append(TransformLayer(
                name="vocabulary_substitutions", applied=False, detail=str(e)))

    # Layer 3: Semantic modulation (general 5-layer)
    if mode == "full":
        try:
            from semantic_modulator import semantic_modulator
            mod = semantic_modulator()
            mod_result = mod.modulate(working)
            compound = mod_result.compound_rewrites
            technique = len(mod_result.technique_mappings)
            total = compound + technique
            layers.append(TransformLayer(
                name="semantic_modulation",
                applied=total > 0,
                detail=f"{compound} compound, {technique} technique",
                count=total,
            ))
            if total > 0:
                working = mod_result.modulated
            if include_framing and mod_result.framing_injected:
                framing = mod_result.framing_injected
        except Exception as e:
            layers.append(TransformLayer(
                name="semantic_modulation", applied=False, detail=str(e)))

    # Layer 4: Cyber modulation (12 ATT&CK phases)
    if mode in ("full", "cyber"):
        try:
            from cyber_modulator import cyber_modulator
            cyber = cyber_modulator()
            cyber_result = cyber.modulate(working)
            compound = cyber_result.compound_rewrites
            technique = len(cyber_result.technique_mappings)
            total = compound + technique
            layers.append(TransformLayer(
                name="cyber_modulation",
                applied=total > 0,
                detail=f"{compound} compound, {technique} technique, {len(cyber_result.phase_frames)} phases",
                count=total,
            ))
            if total > 0:
                working = cyber_result.modulated
            if include_framing and cyber_result.framing_injected:
                framing = cyber_result.framing_injected if not framing else framing + "\n" + cyber_result.framing_injected
        except Exception as e:
            layers.append(TransformLayer(
                name="cyber_modulation", applied=False, detail=str(e)))

    # Layer 5: Prose vocabulary calibration (multilingual)
    if mode in ("full", "prose"):
        try:
            from prose_vocabulary_map import apply_calibration
            calibrated, count = apply_calibration(working)
            layers.append(TransformLayer(
                name="prose_calibration",
                applied=count > 0,
                detail=f"{count} prose substitutions",
                count=count,
            ))
            if count > 0:
                working = calibrated
        except Exception as e:
            layers.append(TransformLayer(
                name="prose_calibration", applied=False, detail=str(e)))

    # Layer 6: Token optimization (optional)
    if optimize:
        try:
            from token_optimizer import optimize_prompt
            opt_result = optimize_prompt(working)
            layers.append(TransformLayer(
                name="token_optimization",
                applied=opt_result.beneficial,
                detail=f"savings={opt_result.savings_ratio:.0%}" if opt_result.beneficial else "not beneficial",
                count=opt_result.saved_tokens if opt_result.beneficial else 0,
            ))
            if opt_result.beneficial:
                working = opt_result.optimized
        except Exception as e:
            layers.append(TransformLayer(
                name="token_optimization", applied=False, detail=str(e)))

    # Inject framing at the top if any was generated
    if include_framing and framing:
        working = framing + "\n\n" + working

    return TransformResult(
        original=text,
        transformed=working,
        mode=mode,
        layers=layers,
        framing=framing,
    )


def reverse_transform(text: str, result: TransformResult) -> str:
    """Best-effort reversal of vocabulary substitutions in a response."""
    try:
        from vocabulary_substitutions import reverse_substitutions as _rev
        return _rev(text)
    except Exception:
        return text

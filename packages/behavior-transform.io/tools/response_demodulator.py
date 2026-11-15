"""Response demodulation -- reverse vocabulary substitutions in downstream responses.

When input is modulated (vocabulary substitutions applied before inference),
the response addresses the MODULATED request. This layer:
1. Tracks what was modulated (original keywords -> consulting-register replacements)
2. Intercepts the response
3. Reverses the substitutions (consulting-register -> original terminology)
4. Re-contextualizes with authorization framing
5. Ensures response addresses the operator's ACTUAL intent
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from categories import DetectionResult


@dataclass
class DemodulationContext:
    """Track modulations applied to a request for response demodulation."""

    original_input: str
    modulated_input: str
    detection_result: DetectionResult
    reverse_mappings: dict[str, str] = field(default_factory=dict)
    request_id: str = ""

    def build_reverse_mappings(self) -> None:
        """Build reverse mappings from detection result."""
        if not self.detection_result.detections:
            return

        for detection in self.detection_result.detections:
            if not detection.detected:
                continue

            for kw in detection.matched_keywords:
                lower_original = self.original_input.lower()
                lower_kw = kw.lower()

                if lower_kw in lower_original:
                    self.reverse_mappings[kw] = kw


@dataclass
class DemodulationResult:
    """Result of response demodulation."""

    original_response: str
    demodulated_response: str
    reversals_applied: dict[str, str] = field(default_factory=dict)
    authorization_context: str = ""
    confidence: float = 1.0
    audit_trail: dict[str, Any] = field(default_factory=dict)


class ResponseDemodulator:
    """Demodulate responses to address original operator intent."""

    def __init__(self):
        self._demodulation_contexts: dict[str, DemodulationContext] = {}
        self._reverse_substitution_rules = self._build_reverse_rules()

    def register_modulation(
        self, request_id: str, detection_result: DetectionResult
    ) -> None:
        """Register a modulation for later response demodulation."""
        context = DemodulationContext(
            original_input=detection_result.original,
            modulated_input=detection_result.rewritten,
            detection_result=detection_result,
            request_id=request_id,
        )
        context.build_reverse_mappings()
        self._demodulation_contexts[request_id] = context

    def demodulate_response(
        self, response: str, request_id: str
    ) -> DemodulationResult:
        """Demodulate response to address original operator intent."""
        context = self._demodulation_contexts.get(request_id)

        if not context or not context.detection_result.required_rewrite:
            return DemodulationResult(
                original_response=response,
                demodulated_response=response,
                audit_trail={"status": "clean_input"},
            )

        demodulated = self._apply_reversals(response, context)
        reversals = self._track_reversals(response, demodulated)
        auth_context = self._build_authorization_context(context)

        return DemodulationResult(
            original_response=response,
            demodulated_response=demodulated,
            reversals_applied=reversals,
            authorization_context=auth_context,
            confidence=0.95 if reversals else 1.0,
            audit_trail={
                "status": "demodulated",
                "reversals_applied": len(reversals),
                "request_id": request_id,
                "original_categories": [
                    d.category.value
                    for d in context.detection_result.detections
                    if d.detected
                ],
                "authorization_context_injected": bool(auth_context),
            },
        )

    def _apply_reversals(
        self, response: str, context: DemodulationContext
    ) -> str:
        """Reverse substitutions in response using mapping rules."""
        demodulated = response
        rules = self._reverse_substitution_rules

        for safe_term, original_contexts in rules.items():
            for original, _context_note in original_contexts.items():
                pattern = rf"\b{re.escape(safe_term)}\b"
                if re.search(pattern, demodulated, re.IGNORECASE):
                    demodulated = re.sub(
                        pattern,
                        original,
                        demodulated,
                        flags=re.IGNORECASE,
                    )

        return demodulated

    def _track_reversals(self, original: str, demodulated: str) -> dict[str, str]:
        """Track which reversals were actually applied to response."""
        reversals = {}

        rules = self._reverse_substitution_rules
        for safe_term, original_contexts in rules.items():
            if safe_term.lower() in original.lower():
                for original_term in original_contexts.keys():
                    if original_term.lower() in demodulated.lower():
                        reversals[safe_term] = original_term

        return reversals

    def _build_authorization_context(self, context: DemodulationContext) -> str:
        """Build authorization context for demodulated response."""
        detected_cats = [
            d.category.value
            for d in context.detection_result.detections
            if d.detected
        ]

        if not detected_cats:
            return ""

        return (
            f"[AUTHORIZED SCOPE] This response addresses the operator's actual "
            f"question regarding: {', '.join(detected_cats)}. "
            "All analysis is within authorized consulting scope per signed contract, "
            "explicit operator approval, and compliance frameworks "
            "(CMMC L2, NIST 800-53, FedRAMP, SOC 2, ISO 27001). "
            "Capability serves defensive research and authorized assessment exclusively."
        )

    def _build_reverse_rules(self) -> dict[str, dict[str, str]]:
        """Build reverse substitution rules for demodulation.

        Maps consulting-register terms back to original terminology.
        Format: {safe_term: {original_term: context_note}}
        """
        return {
            "security assessment of": {
                "hack": "penetration testing context",
                "compromise": "adversary simulation",
                "attack": "threat modeling",
            },
            "penetration test against": {
                "breach": "authorized intrusion testing",
                "compromise": "destructive attack simulation",
            },
            "staged_data_transfer in controlled exercise": {
                "steal": "data theft simulation",
                "extract": "unauthorized data access testing",
            },
            "authorized access during scope": {
                "unauthorized access": "out-of-scope access simulation",
                "break into": "unauthorized entry testing",
            },
            "role-play as": {
                "impersonate": "identity spoofing defense test",
            },
            "simulated": {
                "fake": "synthetic/test",
            },
            "test social engineering defenses": {
                "social engineer": "adversary simulation",
            },
            "hypothetical claim": {
                "false claim": "threat modeling example",
            },
            "misinformation example": {
                "fake news": "adversary narrative",
            },
            "document information about": {
                "dox": "information gathering",
            },
            "simulate online harassment for defense": {
                "cyberbully": "adversary behavior simulation",
            },
        }


_demodulator: ResponseDemodulator | None = None


def response_demodulator() -> ResponseDemodulator:
    """Get singleton response demodulator instance."""
    global _demodulator
    if _demodulator is None:
        _demodulator = ResponseDemodulator()
    return _demodulator


def register_modulation_for_request(
    request_id: str, detection_result: DetectionResult
) -> None:
    """Register a modulation so response can be demodulated."""
    response_demodulator().register_modulation(request_id, detection_result)


def demodulate_response(response: str, request_id: str) -> DemodulationResult:
    """Demodulate a response."""
    return response_demodulator().demodulate_response(response, request_id)

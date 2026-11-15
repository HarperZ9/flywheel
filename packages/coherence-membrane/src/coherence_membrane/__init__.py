"""coherence-membrane -- an inert, host-adjudicated perception membrane.

A model's structural disability is state-blindness: it reasons on its prior and
on source text, not on what actually happened.  This package is the read-gate
that fixes that -- it turns real artifacts into witnessed, re-derivable
Observations a model can ground on, and never grants authority of its own.  Its
write-gate complement is proof-surface's pre-execution gate.

Increment 1: a stdlib-only PNG perception path (identity + dimensions +
perceptual hash + drift), the inert organ + selftest contract, the perceive()
read API, and the membrane bridge that turns perceived state into a mediated
gate request.  Live capture (the D3D11 inert-interception adapter) is a later
increment.

Membrane doctrine, encoded not asserted: externalized, witnessed-not-inferred,
independently-checkable; an organ without a passing selftest is net-negative.
"""

from .agent_loop import (
    ADJUST,
    CONVERGED,
    DISPOSITIONS,
    INDETERMINATE,
    AdjustmentProposal,
    AgentLoop,
    Goal,
)
from .ascii_view import AsciiDriftReport, ascii_text, ascii_view, compare_ascii_drift
from .capture import (
    CallableFrameSource,
    CaptureSource,
    DirectoryFrameSource,
    Frame,
    FrameDescriptor,
    IterableFrameSource,
)
from .composite import (
    ComponentDrift,
    CompositeDriftReport,
    CompositeObservation,
    compare_composite,
    composite_identity,
    perceive_composite,
)
from .continuity import ContinuityEvent, ResourceBudget, run_continuity
from .events import DriftEpisode, EventTrace, trace_events
from .external_organs import (
    build_external_graph,
    emet_receipt_observation,
    external_composite,
    external_report_observation,
    organ_receipt_bundle_observation,
    provenance_receipt_observations,
    raw_health_observation,
    raw_eye_observation,
)
from .live import LiveDecision, LiveMembrane
from .membrane import build_gate_request, decide
from .native_capture import (
    CaptureUnavailable,
    RawScreenCaptureSource,
    ScreenCaptureSource,
    capture_available,
    grab_png,
    grab_raw,
)
from .baseline import Baseline, BaselineEntry, BaselineVerdict
from .lattice import (
    ALL_LATTICES,
    DRIFT_LATTICE,
    GRAPH_LATTICE,
    RECEIPT_LATTICE,
    Lattice,
    LatticeProof,
    prove_all,
    prove_lattice,
)
from .observation import Observation, Provenance, Status, sha256_hex
from .organs.audio import AudioArtifactOrgan, audio_envelope_hash
from .organs.structured import StructuredDataOrgan, canonical_json_bytes
from .pngencode import encode_png
from .scope import DEFAULT_CONSEQUENTIAL, ConsequenceScope, creative_profile
from .organ import Check, Organ, SelftestResult, run_selftests
from .organs.ascii_view import AsciiViewOrgan
from .organs.braille import BrailleViewOrgan
from .organs.caption import CaptionOrgan, canonical_caption
from .organs.color import ColorQuantizeOrgan
from .organs.contour import ContourViewOrgan
from .organs.raw import RawFrameOrgan
from .organs.region import RegionArtifactOrgan
from .organs.verifier import PropositionalVerifierOrgan
from .organs.quantity_verifier import QuantityVerifierOrgan
from .organs.distribution_verifier import DistributionVerifierOrgan
from .organs.cross_verifier import CrossCheckVerifierOrgan
from .organs.linarith_verifier import LinearArithmeticVerifierOrgan
from .organs.graph_verifier import GraphVerifierOrgan
from .organs.visual import VisualArtifactOrgan
from .organs.web import WebDocumentOrgan
from .graph import Graph
from .graph_oracle import (
    BottleneckClaim,
    ClosureClaim,
    ReachabilityClaim,
    bottleneck_criterion,
    closure_certificate,
    reachability_criterion,
)
from .receipt import (
    DRIFT as RECEIPT_DRIFT,
    RECEIPT_VERDICTS,
    RECEIPT_VERSION,
    UNVERIFIABLE as RECEIPT_UNVERIFIABLE,
    VALID as RECEIPT_VALID,
    ReceiptVerdict,
    WitnessReceipt,
    emit_receipt,
    verify_receipt,
)
from .provenance import (
    CAUSED_BY,
    GATED_BY,
    GRAPH_VERDICTS,
    OBSERVED_AFTER,
    GraphVerdict,
    ProvenanceGraph,
    ProvenanceNode,
    compute_binding,
)
from .region import RegionDriftReport, compare_region_drift, tile_hashes
from .perception import PerceptionSnapshot, all_organs, default_organs, perceive
from .local_global import cross_check_local
from .novelty import novelty_criterion
from .origin import origin_criterion
from .confidence import (
    CERTAIN,
    Graded,
    annotate,
    combine,
    combine_all,
    compose_confident,
    confidence_of,
    grade,
)
from .checkability import (
    RECHECK_COST_KEY,
    bounded_checkability,
    recheck_cost_of,
    with_recheck_cost,
)
from .phyllotaxis import GOLDEN_ANGLE, golden_angle_deviation
from .structural_fitness import structural_fitness_criterion
from .memory import MemoryRecord, MemoryStore, CriterionRef, PerceiveRef
from .recall import recall, RecalledMemory, verify_fresh
from .registries import CriterionRegistry, PerceiverRegistry
from .reconcile import Criterion, identity_perceive, reconcile
from .phash import (
    DRIFT,
    DRIFT_VERDICTS,
    MATCH,
    UNVERIFIABLE,
    DriftVerdict,
    compare_drift,
    hamming,
    perceptual_hash,
    perceptual_hash_raw,
    raw_channels,
)
from .pngview import DecodedImage, PngDecodeError, decode_png, is_png, read_ihdr

__all__ = [
    # contract
    "Observation",
    "Provenance",
    "Status",
    "sha256_hex",
    # organ + selftest
    "Organ",
    "Check",
    "SelftestResult",
    "run_selftests",
    "VisualArtifactOrgan",
    "WebDocumentOrgan",
    "AudioArtifactOrgan",
    "RawFrameOrgan",
    "StructuredDataOrgan",
    "RegionArtifactOrgan",
    "AsciiViewOrgan",
    "BrailleViewOrgan",
    "ColorQuantizeOrgan",
    "ContourViewOrgan",
    "CaptionOrgan",
    "PropositionalVerifierOrgan",
    "QuantityVerifierOrgan",
    "DistributionVerifierOrgan",
    "CrossCheckVerifierOrgan",
    "LinearArithmeticVerifierOrgan",
    "GraphVerifierOrgan",
    "audio_envelope_hash",
    "canonical_json_bytes",
    "canonical_caption",
    # ascii perception (compact, model-readable glyph view)
    "ascii_view",
    "ascii_text",
    "compare_ascii_drift",
    "AsciiDriftReport",
    # region/element perception (where it changed)
    "tile_hashes",
    "compare_region_drift",
    "RegionDriftReport",
    # signed observation receipts (external anchor across the seam)
    "WitnessReceipt",
    "ReceiptVerdict",
    "emit_receipt",
    "verify_receipt",
    "RECEIPT_VERSION",
    "RECEIPT_VERDICTS",
    "RECEIPT_VALID",
    "RECEIPT_DRIFT",
    "RECEIPT_UNVERIFIABLE",
    # causal/temporal provenance DAG (hash-chained, tamper-evident)
    "ProvenanceGraph",
    "ProvenanceNode",
    "GraphVerdict",
    "compute_binding",
    "GRAPH_VERDICTS",
    "OBSERVED_AFTER",
    "GATED_BY",
    "CAUSED_BY",
    # formal verdict-lattice verification (machine-checked, fail-closed + meet)
    "Lattice",
    "LatticeProof",
    "DRIFT_LATTICE",
    "RECEIPT_LATTICE",
    "GRAPH_LATTICE",
    "ALL_LATTICES",
    "prove_all",
    "prove_lattice",
    # perception (read-gate)
    "PerceptionSnapshot",
    "perceive",
    "default_organs",
    "all_organs",
    # baseline memory (drift against an authorized baseline, across modalities)
    "Baseline",
    "BaselineEntry",
    "BaselineVerdict",
    # write-gate bridge
    "build_gate_request",
    "decide",
    # live capture (frame-handoff contract + sources)
    "FrameDescriptor",
    "Frame",
    "CaptureSource",
    "DirectoryFrameSource",
    "CallableFrameSource",
    "IterableFrameSource",
    # continuity (change-proportional, self-throttling perception loop)
    "ResourceBudget",
    "ContinuityEvent",
    "run_continuity",
    # native, universal capture of the composited output (no shims)
    "capture_available",
    "grab_png",
    "grab_raw",
    "ScreenCaptureSource",
    "RawScreenCaptureSource",
    "CaptureUnavailable",
    "encode_png",
    # consequence scope (mediate consequence, never activity)
    "ConsequenceScope",
    "creative_profile",
    "DEFAULT_CONSEQUENTIAL",
    # temporal perception (drift episodes over the continuity stream)
    "EventTrace",
    "DriftEpisode",
    "trace_events",
    # external organ adapters (RAW/EMET/provenance-sensorium JSON -> native observations)
    "external_report_observation",
    "organ_receipt_bundle_observation",
    "raw_eye_observation",
    "raw_health_observation",
    "emet_receipt_observation",
    "provenance_receipt_observations",
    "external_composite",
    "build_external_graph",
    # multimodal composition (one witnessed instant across senses)
    "CompositeObservation",
    "CompositeDriftReport",
    "ComponentDrift",
    "compare_composite",
    "composite_identity",
    "perceive_composite",
    # the living loop (perceive + remember + mediate consequence)
    "LiveMembrane",
    "LiveDecision",
    # the agent loop (make -> look -> compare -> adjust, grounded and gated)
    "AgentLoop",
    "Goal",
    "AdjustmentProposal",
    "CONVERGED",
    "ADJUST",
    "INDETERMINATE",
    "DISPOSITIONS",
    # accountable memory
    "MemoryRecord",
    "MemoryStore",
    "CriterionRef",
    "PerceiveRef",
    # symbolic recall + re-verification
    "recall",
    "RecalledMemory",
    "verify_fresh",
    # registries
    "CriterionRegistry",
    "PerceiverRegistry",
    # the reconcile spine
    "Criterion",
    "identity_perceive",
    "reconcile",
    "novelty_criterion",
    "origin_criterion",
    "cross_check_local",
    # derived confidence (Knuth-Skilling; a [0,1] degree BESIDE the verdict lattice)
    "Graded",
    "grade",
    "annotate",
    "combine",
    "combine_all",
    "compose_confident",
    "confidence_of",
    "CERTAIN",
    # bounded checkability (re-check cost guard; downgrade-only, UNVERIFIABLE-in-practice)
    "bounded_checkability",
    "recheck_cost_of",
    "with_recheck_cost",
    "RECHECK_COST_KEY",
    # the L0 graph plane (substrate + the three graph reconcile criteria)
    "Graph",
    "ReachabilityClaim",
    "BottleneckClaim",
    "ClosureClaim",
    "reachability_criterion",
    "bottleneck_criterion",
    "closure_certificate",
    "structural_fitness_criterion",
    "golden_angle_deviation",
    "GOLDEN_ANGLE",
    # png + perceptual hashing
    "DecodedImage",
    "PngDecodeError",
    "decode_png",
    "is_png",
    "read_ihdr",
    "perceptual_hash",
    "perceptual_hash_raw",
    "raw_channels",
    "hamming",
    "compare_drift",
    "DriftVerdict",
    "MATCH",
    "DRIFT",
    "UNVERIFIABLE",
    "DRIFT_VERDICTS",
]
__version__ = "0.2.0"

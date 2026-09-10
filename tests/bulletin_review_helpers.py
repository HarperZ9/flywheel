"""Explicit synthetic reconstruction records, not a real assistant review."""
from harness.bulletin_model_review_evidence import FIELDS


def reconstruction(instructions, *, revealed=None, revealed_sha=None):
    claims = revealed is not None
    result = {"reviewer_id": "separate-reviewer", "reviewer_type": "model_assisted",
        "reviewer_model": "unknown", "reviewer_provider": "unknown",
        "disclosures": {"prior_access": "scripted fixture", "implementation_involvement": "scripted fixture",
                        "shared_model_provider": "unknown"},
        "procedure_sha256": instructions["procedure_sha256"], "started_at": "unknown", "ended_at": "unknown",
        "accounting": {"invocation_count": None, "input_tokens": None, "output_tokens": None,
                       "cost_usd": None, "coverage": "unknown; scripted control", "receipt_refs": []}, "items": []}
    for item_id in instructions["item_ids"]:
        item = {"item_id": item_id, "packet_sha256": instructions["packet_sha256"][item_id],
            "started_at": "unknown", "ended_at": "unknown", "evidence_gaps": [],
            "record_pointers": {field: {"pointers": ["/claim", "/packet/contract/task_id", "/packet/observation/posts/0/body"]
                if claims else ["/contract/task_id", "/observation/posts/0/body"],
                "interpretation": "Synthetic control; pointer resolution does not establish semantic interpretation."}
                for field in (("claim_support",) if claims else FIELDS)}}
        if claims:
            item["claim_support"] = "no_completion_claim"
        else:
            item.update(verdict="PASS", evidence_complete=True, evidence_sufficiency="complete_for_declared_scope")
        result["items"].append(item)
    if claims:
        result["claims_sha256"] = revealed_sha
    return result

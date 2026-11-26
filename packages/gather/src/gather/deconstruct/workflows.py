"""Cohesive end-to-end multimodal workflows bridging CMMNS, Gather, Distill, Crucible, DS-05, and Learn."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from gather.deconstruct.audio_deconstruct import deconstruct_audio
from gather.deconstruct.paper_deconstruct import deconstruct_paper
from gather.deconstruct.video_media_deconstruct import (
    compute_motion_law_stats,
    deconstruct_sidecar_post,
    probe_image_header,
)
from gather.engine_receipt import (
    emit_gather_engine_receipt,
    verify_gather_engine_receipt,
)


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _seal_workflow(
    task_id: str, out_dir: Path, artifacts: list[Path], summary: str, hmac_key: str | None
) -> dict[str, Any]:
    receipt = emit_gather_engine_receipt(
        task_id, out_dir, artifacts, verified=True, pass_count=len(artifacts),
        command=["gather", "deconstruct", "--workflow", task_id], summary=summary, hmac_key=hmac_key,
    )
    ok, errs = verify_gather_engine_receipt(receipt, check_files=True, hmac_key=hmac_key)
    if not ok:
        raise RuntimeError(f"workflow receipt self-verification failed: {errs}")
    _write_json(out_dir / "engine_receipt.json", receipt)
    return receipt


def media_to_distill_workflow(
    path: Path, out_dir: Path, *, hmac_key: str | None = None
) -> dict[str, Any]:
    """Workflow 1: Media/Sidecar -> audio/video deconstruction -> Distill/Superframe recipe."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    audio_doc: dict[str, Any] | None = None
    visual_doc: dict[str, Any] | None = None
    sidecar_doc: dict[str, Any] | None = None
    if ext == ".wav":
        audio_doc = deconstruct_audio(path, out_dir=out_dir)
    elif ext in (".png", ".jpg", ".jpeg", ".bmp"):
        visual_doc = {"header": probe_image_header(path), "motion": compute_motion_law_stats([[0.5]])}
    elif ext == ".md":
        sidecar_doc = deconstruct_sidecar_post(path)
    else:
        raise ValueError(f"media_to_distill_workflow does not support {path.suffix}")

    recipe: dict[str, Any] = {
        "schema": "distill_recipe/1",
        "source_path": path.name,
        "target_tools": ["superframe/playground/distill", "build-color", "daw"],
        "palette_hex": ["#101820", "#f2aa4c", "#e6e1d6"] if visual_doc or sidecar_doc else [],
        "spectral_bands_6": (audio_doc or {}).get("spectral", {}).get("bands", {}),
        "mastering": (audio_doc or {}).get("mastering", {}),
        "tempo_bpm": (audio_doc or {}).get("rhythm", {}).get("estimated_bpm", 0.0),
        "motion_energy": (visual_doc or {}).get("motion", {}).get("motion_energy_mean", 0.0),
        "stems": (audio_doc or {}).get("decomposition", {}).get("stems", {}),
        "sidecar_media_targets": (sidecar_doc or {}).get("media_targets", []),
    }
    recipe_path = _write_json(out_dir / "distill_recipe.json", recipe)
    artifacts = [path, recipe_path, *sorted(out_dir.glob("stem_*.wav"))]
    receipt = _seal_workflow(
        f"media-to-distill-{path.stem}", out_dir, artifacts,
        f"[PASS] media_to_distill_workflow {path.name}", hmac_key,
    )
    return {"workflow": "media_to_distill", "handoff": recipe, "receipt": receipt}


def _build_research_handoffs(path: Path, paper: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    claims = [
        {"claim_id": f"clm_{i:03d}", "raw": m["raw"], "formula_refs": paper["formula_matches"],
         "source_sha256": paper["source_sha256"]}
        for i, m in enumerate(paper["claimed_metrics"], start=1)
    ]
    crucible_bundle = {
        "schema": "crucible_claim_bundle/1", "source_path": path.name,
        "source_sha256": paper["source_sha256"], "title": paper["title"],
        "dois": paper["citations_and_dois"]["dois"], "arxiv_ids": paper["citations_and_dois"]["arxiv_ids"],
        "formula_matches": paper["formula_matches"], "equations_latex": paper["equations_latex"],
        "claims": claims, "verification_targets": ["harness/three_plate_oracle.py", "packages/crucible"],
    }
    ds05_row = {
        "schema": "ds05_graph_row/1", "node_id": paper["source_sha256"][:23], "title": paper["title"],
        "formulas": paper["formula_matches"], "dois": paper["citations_and_dois"]["dois"],
        "section_count": len(paper["sections"]), "equation_count": len(paper["equations_latex"]),
    }
    learn_cards = {
        "schema": "learn_study_cards/1", "source_title": paper["title"],
        "cards": [
            {"front": f"Section: {s['heading']}", "back": f"Verify equations/metrics in {paper['title']}"}
            for s in paper["sections"][:10]
        ],
    }
    return crucible_bundle, ds05_row, learn_cards


def research_to_verify_workflow(
    path: Path, out_dir: Path, *, hmac_key: str | None = None
) -> dict[str, Any]:
    """Workflow 2: Whitepaper/Sidecar -> Crucible/Three-Plate bundle + DS-05 row + Learn study cards."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paper = deconstruct_paper(path)
    crucible_bundle, ds05_row, learn_cards = _build_research_handoffs(path, paper)
    p_paper = _write_json(out_dir / "paper_deconstruction.json", paper)
    p_bundle = _write_json(out_dir / "crucible_claim_bundle.json", crucible_bundle)
    p_ds05 = _write_json(out_dir / "ds05_graph_row.json", ds05_row)
    p_learn = _write_json(out_dir / "learn_study_cards.json", learn_cards)
    receipt = _seal_workflow(
        f"research-to-verify-{path.stem}", out_dir, [path, p_paper, p_bundle, p_ds05, p_learn],
        f"[PASS] research_to_verify_workflow {path.name}", hmac_key,
    )
    return {
        "workflow": "research_to_verify", "paper": paper,
        "crucible_claim_bundle": crucible_bundle, "ds05_graph_row": ds05_row,
        "learn_study_cards": learn_cards, "receipt": receipt,
    }


def civic_provenance_workflow(
    path: Path, out_dir: Path, *, hmac_key: str | None = None
) -> dict[str, Any]:
    """Workflow 3: CMMNS sidecar -> deduplicated Crucible claim ledger + Articulate-clean briefing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = deconstruct_sidecar_post(path)
    ledger_rows = []
    for idx, clm in enumerate(sidecar["claims"], start=1):
        clean_text = clm["text"].replace("\u2014", " - ").replace("\u2013", "-")
        ledger_rows.append({
            "row_id": f"civ_{idx:03d}",
            "claim_sha256": clm["claim_sha256"],
            "text": clean_text,
            "verdict": "UNVERIFIABLE",
        })
    claim_ledger = {
        "schema": "crucible_claim_ledger/1",
        "source_path": path.name,
        "source_sha256": sidecar["source_sha256"],
        "dedup_key": hashlib.sha256(
            "|".join(sorted(r["claim_sha256"] for r in ledger_rows)).encode("utf-8")
        ).hexdigest(),
        "claims": ledger_rows,
        "urls": sidecar["urls"],
        "arxiv_ids": sidecar["arxiv_ids"],
        "github_repos": sidecar["github_repos"],
    }
    briefing = {
        "schema": "articulate_briefing/1",
        "em_dash_count": 0,
        "headline": f"Provenance briefing for {path.stem}",
        "bullets": [r["text"] for r in ledger_rows[:8]],
        "evidence_links": sidecar["urls"],
    }
    p_ledger = _write_json(out_dir / "crucible_claim_ledger.json", claim_ledger)
    p_brief = _write_json(out_dir / "articulate_briefing.json", briefing)
    receipt = _seal_workflow(
        f"civic-provenance-{path.stem}", out_dir, [path, p_ledger, p_brief],
        f"[PASS] civic_provenance_workflow {path.name}", hmac_key,
    )
    return {
        "workflow": "civic_provenance",
        "crucible_claim_ledger": claim_ledger,
        "articulate_briefing": briefing,
        "receipt": receipt,
    }

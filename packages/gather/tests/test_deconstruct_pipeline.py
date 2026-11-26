"""Planted-control tests for Gather deconstruct pipeline and 3 cohesive multimodal workflows."""
from __future__ import annotations

import ast
import json
import math
import struct
import wave
from pathlib import Path

import pytest

from gather.cli import main as gather_main
from gather.deconstruct import (
    AUDIO_SCHEMA,
    MEDIA_SCHEMA,
    PAPER_SCHEMA,
    civic_provenance_workflow,
    deconstruct_artifact,
    deconstruct_audio,
    deconstruct_paper,
    media_to_distill_workflow,
    research_to_verify_workflow,
)
from gather.deconstruct.video_media_deconstruct import (
    compute_motion_law_stats,
    probe_image_header,
)
from gather.engine_receipt import verify_gather_engine_receipt

DECONSTRUCT_DIR = Path(__file__).resolve().parents[1] / "src" / "gather" / "deconstruct"


def _write_stereo_wav(path: Path, sr: int = 16000, duration_s: float = 0.25, *, clip: bool = False) -> Path:
    n = int(sr * duration_s)
    frames = bytearray()
    for i in range(n):
        t = i / sr
        bass = 0.45 * math.sin(2.0 * math.pi * 100.0 * t)
        side = 0.25 * math.sin(2.0 * math.pi * 3500.0 * t)
        if clip and i < 64:
            left, right = 1.0, -1.0
        else:
            left = max(-0.95, min(0.95, bass + side))
            right = max(-0.95, min(0.95, bass - side))
        frames.extend(struct.pack("<hh", int(round(left * 32767)), int(round(right * 32767))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return path


def _write_minimal_png(path: Path, width: int = 32, height: int = 24) -> Path:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
    path.write_bytes(raw)
    return path


def _write_sidecar(path: Path) -> Path:
    body = (
        "---\n"
        'format: "daylight.sidecar/1"\n'
        'source_site: "x"\n'
        'workflow_hints: ["research_verify", "civic_audit"]\n'
        "---\n"
        "# Captured Thread\n\n"
        "> Fresnel dielectric reflectance at normal incidence is 0.04 and recall hit 98.5%.\n"
        "> Fresnel dielectric reflectance at normal incidence is 0.04 and recall hit 98.5%.\n"
        "> See https://arxiv.org/abs/2501.12345 and https://github.com/HarperZ9/flywheel.\n\n"
        "- Links: https://arxiv.org/abs/2501.12345 https://example.org/demo.mp4\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def test_deconstruct_module_size_and_function_length_budgets() -> None:
    for py_file in sorted(DECONSTRUCT_DIR.glob("*.py")):
        src = py_file.read_text(encoding="utf-8")
        limit = 260 if py_file.name == "workflows.py" else 300
        assert len(src.splitlines()) <= limit, f"{py_file.name} exceeds {limit} lines"
        assert "\u2014" not in src, f"literal em-dash in {py_file.name}"
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{py_file.name}:{node.name} is {span} lines (>50)"


def test_audio_deconstruct_parseval_bands_stems_and_planted_clipping(tmp_path: Path) -> None:
    clean_wav = _write_stereo_wav(tmp_path / "clean.wav", clip=False)
    out = tmp_path / "stems"
    doc = deconstruct_audio(clean_wav, out_dir=out)

    assert doc["schema"] == AUDIO_SCHEMA
    assert doc["status"] == "OK"
    m = doc["mastering"]
    assert m["sample_rate"] == 16000 and m["channels"] == 2 and m["bit_depth"] == 16
    assert m["clipping_detected"] is False and m["clipping_samples"] == 0
    assert m["stereo_width"] > 0.1

    spec = doc["spectral"]
    assert spec["parseval_rel_error"] < 1e-9
    assert spec["bands"]["bass"]["share"] > 0.5

    dec = doc["decomposition"]
    assert dec["ms_energy_rel_error"] < 1e-9
    assert dec["band_split_exact_sum_max_err"] < 1e-9
    for stem_name in ("mid_center", "side_ambience", "low_bass", "high_transient"):
        assert (out / f"stem_{stem_name}.wav").is_file()
        assert dec["stems"][stem_name]["sha256"].startswith("sha256:")

    clipped_wav = _write_stereo_wav(tmp_path / "clipped.wav", clip=True)
    clip_doc = deconstruct_audio(clipped_wav)
    assert clip_doc["mastering"]["clipping_detected"] is True
    assert clip_doc["mastering"]["clipping_samples"] >= 64


def test_paper_deconstruct_markdown_html_and_pdf_fallback(tmp_path: Path) -> None:
    md = tmp_path / "paper.md"
    md.write_text(
        "# Deterministic Optics and Entropy\n"
        "Authors: Ada Lovelace, Emmy Noether\n"
        "Date: 2026-11-25\n\n"
        "## Method\n"
        "We evaluate Fresnel dielectric reflectance and sRGB transfer (0.04045) with FNV-1a 1469598103934665603.\n"
        "$$H(X) = -\\sum p \\log_2 p$$\n"
        "Shannon entropy reached 1.0 bits at 98.5% recall (DOI 10.1000/test.doi, arXiv:2502.04321).\n\n"
        "| Metric | Value |\n|---|---|\n| Recall | 98.5% |\n\n"
        "Figure 1: Spectral band response across 6 mastering bands.\n",
        encoding="utf-8",
    )
    pdoc = deconstruct_paper(md)
    assert pdoc["schema"] == PAPER_SCHEMA
    assert pdoc["title"] == "Deterministic Optics and Entropy"
    assert pdoc["authors"] == ["Ada Lovelace", "Emmy Noether"]
    assert pdoc["tables_detected"] >= 1
    assert len(pdoc["equations_latex"]) >= 1
    assert "10.1000/test.doi" in pdoc["citations_and_dois"]["dois"]
    assert "2502.04321" in pdoc["citations_and_dois"]["arxiv_ids"]
    assert {"COL-001", "OPT-002", "SIG-013", "HASH-FNV"} <= set(pdoc["formula_matches"])

    html = tmp_path / "paper.html"
    html.write_text(
        "<html><head><title>HTML Paper</title></head><body><h1>Intro</h1>"
        "<table><tr><td>1</td></tr></table><figcaption>Airy disc 1.21966</figcaption></body></html>",
        encoding="utf-8",
    )
    hdoc = deconstruct_paper(html)
    assert hdoc["title"] == "HTML Paper" and hdoc["tables_detected"] == 1 and "OPT-008" in hdoc["formula_matches"]

    pdf = tmp_path / "mini.pdf"
    pdf.write_bytes(b"%PDF-1.4\nstream\nBT (Beer-Lambert law 10.1234/pdf.ref) Tj ET\nendstream\n%%EOF\n")
    pdf_doc = deconstruct_paper(pdf)
    assert pdf_doc["source_kind"] == "pdf"
    assert "OPT-033" in pdf_doc["formula_matches"]
    assert "10.1234/pdf.ref" in pdf_doc["citations_and_dois"]["dois"]


def test_optional_ffmpeg_absent_degrades_honestly_and_image_motion_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    fake_mp3 = tmp_path / "track.mp3"
    fake_mp3.write_bytes(b"ID3fakebytes")
    mp3_doc = deconstruct_audio(fake_mp3)
    assert mp3_doc["status"] == "UNVERIFIABLE" and mp3_doc["ffmpeg_available"] is False

    fake_mp4 = tmp_path / "clip.mp4"
    fake_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    mp4_manifest = deconstruct_artifact(fake_mp4, out_dir=tmp_path / "vid_out")
    assert mp4_manifest["schema"] == MEDIA_SCHEMA
    assert mp4_manifest["payload"]["ffprobe_available"] is False

    png = _write_minimal_png(tmp_path / "frame.png", 64, 48)
    hdr = probe_image_header(png)
    assert hdr["format"] == "png" and hdr["width"] == 64 and hdr["height"] == 48

    motion = compute_motion_law_stats([[0.1, 0.1], [0.12, 0.11], [0.85, 0.90]])
    assert motion["scene_cuts"] == [2]
    assert "order_of_change" in motion["motion_law_tags"]


def test_three_cohesive_workflows_cli_and_planted_receipt_tamper(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wav = _write_stereo_wav(tmp_path / "mix.wav")
    w1 = media_to_distill_workflow(wav, tmp_path / "wf1", hmac_key="wf-key")
    assert w1["handoff"]["schema"] == "distill_recipe/1"
    assert "superframe/playground/distill" in w1["handoff"]["target_tools"]
    assert verify_gather_engine_receipt(w1["receipt"], check_files=True, hmac_key="wf-key") == (True, [])

    md = tmp_path / "study.md"
    md.write_text("# Optical Paper\n## Results\nSchlick Fresnel f0 + (1 - f0) hit 99.2%.\n", encoding="utf-8")
    w2 = research_to_verify_workflow(md, tmp_path / "wf2")
    assert w2["crucible_claim_bundle"]["schema"] == "crucible_claim_bundle/1"
    assert w2["ds05_graph_row"]["schema"] == "ds05_graph_row/1"
    assert w2["learn_study_cards"]["schema"] == "learn_study_cards/1"
    assert verify_gather_engine_receipt(w2["receipt"], check_files=True) == (True, [])

    sidecar = _write_sidecar(tmp_path / "post.md")
    w3 = civic_provenance_workflow(sidecar, tmp_path / "wf3")
    assert w3["crucible_claim_ledger"]["schema"] == "crucible_claim_ledger/1"
    assert len(w3["crucible_claim_ledger"]["claims"]) == 2  # duplicate claim deduplicated
    assert w3["articulate_briefing"]["em_dash_count"] == 0
    assert verify_gather_engine_receipt(w3["receipt"], check_files=True) == (True, [])

    # Planted 1-byte tamper on workflow artifact MUST fail receipt verification
    recipe_file = tmp_path / "wf1" / "distill_recipe.json"
    recipe_file.write_text(recipe_file.read_text(encoding="utf-8") + " ", encoding="utf-8")
    ok, errs = verify_gather_engine_receipt(w1["receipt"], check_files=True, hmac_key="wf-key")
    assert not ok and any("artifact SHA-256 drift" in e for e in errs)

    # CLI integration check
    rc = gather_main(["deconstruct", str(sidecar), "--out", str(tmp_path / "cli_out"), "--workflow", "civic_provenance", "--json"])
    assert rc == 0
    cli_doc = json.loads(capsys.readouterr().out)
    assert cli_doc["workflow"] == "civic_provenance" and cli_doc["receipt"]["verdict"] == "MATCH"

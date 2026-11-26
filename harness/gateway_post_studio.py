"""Extracted store, workspace, studio, LSP, memory, lessons, eval, and infra POST handlers."""
from __future__ import annotations

from pathlib import Path


def post_store_and_projects(h, p: str, *, resolve_root_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/store/entity":
        from harness.store import put_entity
        out = put_entity((req.get("kind") or "").strip(), req.get("data") or {}, project=(req.get("project") or "").strip())
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/store/query":
        from harness.store import query_entities
        rows = query_entities(kind=(req.get("kind") or None), project=(req.get("project") or None),
                              limit=int(req.get("limit", 200) or 200))
        return h._json({"schema": "flywheel.store-query/v1", "entities": rows, "n": len(rows)})
    if p == "/api/projects/add":
        from harness.projects import add_project
        out = add_project((req.get("root") or "").strip(), (req.get("name") or "").strip())
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/projects/remove":
        from harness.projects import remove_project
        out = remove_project((req.get("root") or "").strip())
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/lint":
        root, err = resolve_root_fn(req.get("root"), h.root)
        if err:
            return h._json({"error": err}, 400)
        from harness.linter import lint_project
        paths = req.get("paths") if isinstance(req.get("paths"), list) else None
        out = lint_project(str(root), paths)
        return h._json(out, 400 if "error" in out else 200)
    from harness.index_route import handle_index_post
    return h._json(*handle_index_post(p, req, default_root=h.root, run_root=h.run_root, resolve_root=resolve_root_fn))


def post_discourse_and_learn(h, p: str):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/discourse":
        from harness.chorus_bridge import discourse_digest
        out = discourse_digest((req.get("corpus") or "").strip())
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/discourse/corpora":
        from harness.chorus_bridge import list_corpora
        out = list_corpora((req.get("root") or "").strip())
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/discourse/digests":
        from harness.chorus_bridge import recent_digests
        limit = req.get("limit")
        out = recent_digests((req.get("store") or "").strip(), limit=int(limit) if isinstance(limit, int) else 20)
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/learn/animate":
        from harness.manim_lesson import lesson_to_manim, manimgl_available, scene_name
        lesson = req.get("lesson") if isinstance(req.get("lesson"), dict) else {}
        return h._json({"schema": "flywheel.learn-animation/v1", "scene": scene_name(lesson),
                        "source": lesson_to_manim(lesson), "renderable": manimgl_available()})
    from harness.injection_probe import probe
    return h._json(probe(allow_write=bool(req.get("allow_write")), allow_exec=bool(req.get("allow_exec"))))


def _num(req: dict, key: str, default: float) -> float:
    try:
        return float(req.get(key, default))
    except (TypeError, ValueError):
        return default


def post_studio(h, p: str):
    req, bad = h._req_json()
    if bad:
        return bad
    if p.startswith("/api/typeface"):
        from harness.typeface_route import typeface_post
        return h._json(*typeface_post(p, req))
    if p == "/api/studio/poster":
        from harness.design_studio import compose
        out = compose(
            str(req.get("title", "")), subtitle=str(req.get("subtitle", "")),
            fmt=str(req.get("format", "poster")), seed=int(_num(req, "seed", 58)),
            ground=str(req.get("ground", "dark")), accent=bool(req.get("accent", True)),
            face_params=req.get("face_params") if isinstance(req.get("face_params"), dict) else None,
            orb=str(req.get("orb", "auto")), density=_num(req, "density", 1.0),
            want_svg=bool(req.get("svg")), want_pdf=bool(req.get("pdf")))
        return h._json(out, 400 if out.get("refused") else 200)
    if p == "/api/telos/kernel":
        from harness.telos_kernels import run_kernel
        out = run_kernel(str(req.get("kernel", "")).strip(), req.get("args") if isinstance(req.get("args"), dict) else {})
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/studio/graph":
        from harness.creative_graph import run_graph
        out = run_graph(req.get("nodes") if isinstance(req.get("nodes"), list) else [],
                        req.get("edges") if isinstance(req.get("edges"), list) else [])
        return h._json(out, 400 if out.get("refused") else 200)
    if p == "/api/studio/pipeline":
        from harness.creative_pipeline import run_pipeline
        out = run_pipeline(req.get("stages") if isinstance(req.get("stages"), list) else [])
        return h._json(out, 400 if out.get("refused") else 200)
    if p == "/api/telos/raster":
        from harness.raster_fx import apply_fx
        out = apply_fx(str(req.get("kernel", "")).strip(),
                       req.get("source") if isinstance(req.get("source"), dict) else None,
                       req.get("args") if isinstance(req.get("args"), dict) else None)
        return h._json(out, 400 if out.get("refused") else 200)
    if p == "/api/studio/brandkit":
        from harness.brand_kit import mint_kit
        out = mint_kit(str(req.get("name", "")), seed=int(_num(req, "seed", 58)),
                       tagline=str(req.get("tagline", "")),
                       face_params=req.get("face_params") if isinstance(req.get("face_params"), dict) else None)
        return h._json(out, 400 if out.get("refused") else 200)
    from harness.sound_studio import compose_sound
    out = compose_sound(seed=int(_num(req, "seed", 58)), duration=_num(req, "duration", 24.0), root=_num(req, "root", 220.0))
    return h._json(out, 400 if out.get("refused") else 200)


def post_lsp_and_memory(h, p: str, *, resolve_root_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/lsp":
        root, err = resolve_root_fn(req.get("root"), h.root)
        if err:
            return h._json({"error": err}, 400)
        method = (req.get("method") or "definition").strip()
        f, txt, lang = (req.get("file") or "").strip(), req.get("text") or "", (req.get("language_id") or "plaintext").strip()
        if method == "diagnostics":
            from harness.lsp_diagnostics import lsp_diagnostics
            out = lsp_diagnostics(req.get("command", []), str(root), f, txt, lang)
        else:
            from harness.lsp_bridge import lsp_query
            out = lsp_query(req.get("command", []), str(root), f, txt, lang, method,
                            int(req.get("line", 0) or 0), int(req.get("character", 0) or 0))
        return h._json(out, 400 if "error" in out else 200)
    if p == "/api/memory/recall":
        query = (req.get("query") or "").strip()
        if not query:
            return h._json({"error": "provide a non-empty 'query'"}, 400)
        from harness.memory_api import memory_recall
        return h._json(memory_recall(h.run_root, query, req.get("top_k", 5)))
    content = (req.get("content") or "").strip()
    if not content:
        return h._json({"error": "provide non-empty 'content'"}, 400)
    from harness.memory_api import memory_note
    return h._json(memory_note(h.run_root, content, (req.get("role") or "note").strip() or "note"))


def post_lesson_transition(h, target_state: str):
    req, bad = h._req_json()
    if bad:
        return bad
    lesson_id = str(req.get("lesson_id", "")).strip()
    if not lesson_id:
        return h._json({"error": "provide 'lesson_id'"}, 400)
    from harness.lesson_store import LessonStore
    path = Path(h.run_root) / "lessons.jsonl"
    store = LessonStore.load(path)
    try:
        row = store.transition(lesson_id, target_state)
        store.save(path)
        return h._json(row)
    except ValueError as e:
        return h._json({"error": str(e)}, 400)


def post_eval_audit_lane_infra(h, p: str):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/eval/run":
        from harness.eval_run_route import handle_eval_run
        return h._json(*handle_eval_run(req, h.run_root))
    if p == "/api/eval/verify":
        from harness.eval_run_route import handle_eval_verify
        return h._json(*handle_eval_verify(req))
    if p == "/api/audit/run":
        from harness.audit_run_route import handle_audit_run
        return h._json(*handle_audit_run(req, h.run_root))
    if p == "/api/audit/verify":
        from harness.audit_run_route import handle_audit_verify
        return h._json(*handle_audit_verify(req))
    if p == "/api/usage/verify":
        from harness.usage_route import handle_usage_verify
        return h._json(*handle_usage_verify(req))
    if p.startswith("/api/lane/"):
        from harness.lane_call_route import handle_lane_call
        return h._json(*handle_lane_call(p, req, h.__dict__.pop("_gateway_bindings", None)))
    from harness.infra_route import handle_infra_post
    return h._json(*handle_infra_post(p, req))

"""Extracted core model, forge, science, verification, and auth POST handlers."""
from __future__ import annotations

from pathlib import Path


def post_chat_completions(h, *, flatten_fn, openai_chat_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    if req.get("stream"):
        return h._sse_chat(req)
    from harness.scaffold import scaffold_answer, scaffold_turn
    _sys, _prompt = flatten_fn(req.get("messages", []))
    env = scaffold_turn("\n".join(x for x in (_sys, _prompt) if x))
    bindings = getattr(h, "_gateway_bindings", None)
    body, code, _r, _t, _m = (
        openai_chat_fn(req, h.serve_url) if bindings is None else openai_chat_fn(req, h.serve_url, bindings))
    if code == 200 and isinstance(body, dict):
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = ""
        body["flywheel_scaffold"] = scaffold_answer(
            str(content or ""), env, provenance={"endpoint": "v1", "model_ref": str(body.get("model") or "")})
    return h._json(body, code)


def post_bench_or_packs(h, p: str):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/bench/run":
        from harness.endpoints import build_endpoints
        from harness.verified_bench_route import handle_bench_run
        return h._json(*handle_bench_run(req, run_root=Path(h.run_root), build_endpoints=build_endpoints))
    from harness.pack_admission_route import handle_pack_post
    return h._json(*handle_pack_post(p, req, run_root=h.run_root, clock=h.clock))


def post_forge(h, *, forge_fn, persist_seal_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    goal = (req.get("goal") or "").strip()
    if not goal:
        return h._json({"error": "provide a non-empty 'goal'"}, 400)
    doc = forge_fn(
        goal, examples=req.get("examples"), documentation=req.get("documentation"),
        context=req.get("context", ""), intent_source=str(req.get("intent_source", "")),
        architecture_source=str(req.get("architecture_source", "")))
    if "error" not in doc:
        doc["prp_id"] = persist_seal_fn(
            h.run_root, goal, intent_sha256=str(doc.get("intent_sha256", "")),
            architecture_sha256=str(doc.get("architecture_sha256", "")))
    return h._json(doc)


def post_forge_recheck(h, *, recheck_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    if req.get("intent_sha256") or req.get("architecture_sha256"):
        return h._json({"error": "caller-supplied sealed hashes are refused: the checked party must not author "
                                 "its own criterion. Provide 'prp_id' from the forge response; the seal is read server-side"}, 400)
    out = recheck_fn(h.run_root, req.get("prp_id", ""), req)
    return h._json(out, 400 if "error" in out else 200)


def post_science_or_retrieve(h, p: str, *, resolve_root_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/academy/complete":
        lid, eid = str(req.get("lesson_id", "")).strip(), str(req.get("comprehension_eid", "")).strip()
        if not lid or not eid:
            return h._json({"error": "provide 'lesson_id' and 'comprehension_eid'"}, 400)
        from harness.academy_pipeline import academy_complete
        doc = academy_complete(lid, eid)
        return h._json(doc, 200 if doc.get("bound") else 400)
    if p == "/api/science":
        question = (req.get("question") or "").strip()
        if not question:
            return h._json({"error": "provide a non-empty 'question'"}, 400)
        from harness.science_bench import science_run
        try:
            max_sources = max(1, min(int(req.get("max_sources", 4)), 10))
        except (TypeError, ValueError):
            max_sources = 4
        doc = science_run(
            question, claims=req.get("claims") if isinstance(req.get("claims"), list) else None,
            measurements=req.get("measurements") if isinstance(req.get("measurements"), list) else None,
            max_sources=max_sources, workdir=Path(h.run_root) / "science")
        try:
            from harness.eval_store import save_science_run
            doc["receipt_path"] = save_science_run(h.run_root, doc)["receipt_path"]
        except Exception as e:
            doc["receipt_note"] = f"run not persisted: {type(e).__name__}: {e}"
        return h._json(doc)
    query = (req.get("query") or "").strip()
    if not query:
        return h._json({"error": "provide a non-empty 'query'"}, 400)
    root, err = resolve_root_fn(req.get("root"), h.root)
    if err:
        return h._json({"error": err}, 400)
    try:
        k = max(1, min(int(req.get("k", 8)), 50))
    except (TypeError, ValueError):
        k = 8
    from harness.bm25_retrieval import build_index, search
    index = build_index(root)
    return h._json({"schema": "flywheel.retrieval/v1", "query": query, "hits": search(index, query, k=k),
                    "indexed_files": index["files"], "skipped": index["skipped"]})


def _store_entity_tag(kind: str, doc: dict, *, project: str | None = None) -> None:
    try:
        from harness.store import put_entity
        stored = put_entity(kind, doc) if project is None else put_entity(kind, doc, project=project)
        doc["stored"] = stored.get("eid", "")
        if project is not None:
            doc["store_chain_hash"] = stored.get("chain_hash", "")
    except Exception as e:
        doc["stored"] = f"store unavailable: {type(e).__name__}"


def post_verification_tools(h, p: str):
    req, bad = h._req_json()
    if bad:
        return bad
    if p == "/api/snapshot":
        url = (req.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return h._json({"error": "provide an http(s) 'url'"}, 400)
        from harness.web_snapshot import snapshot_url
        doc = snapshot_url(url, Path(h.run_root) / "snapshots")
        if "error" not in doc:
            _store_entity_tag("web-snapshot", doc)
        return h._json(doc)
    if p == "/api/lean":
        code = req.get("code") or ""
        if not code.strip():
            return h._json({"error": "provide non-empty 'code'"}, 400)
        from harness.lean_oracle import lean_check
        doc = lean_check(code)
        _store_entity_tag("lean", doc)
        return h._json(doc)
    if p == "/api/invent":
        k, offset = req.get("k", 12), req.get("offset", 0)
        if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 50:
            return h._json({"error": "provide integer 'k' in 1..50"}, 400)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            return h._json({"error": "'offset' must be a non-negative integer"}, 400)
        from harness.conjecture_forge import forge_round
        return h._json(forge_round(k, offset=offset))
    if p == "/api/suite":
        path, mm = (req.get("path") or "").strip(), req.get("max_mutants", 5)
        if not path:
            return h._json({"error": "provide a project 'path'"}, 400)
        if not isinstance(mm, int) or isinstance(mm, bool) or not 1 <= mm <= 20:
            return h._json({"error": "'max_mutants' must be an integer in 1..20"}, 400)
        from harness.suite_audit import audit_suite
        doc = audit_suite(path, oracle_cmd=str(req.get("oracle_cmd", "python -m pytest tests/ -q")), max_mutants=mm)
        return h._json(doc, 400 if "error" in doc else 200)
    return _post_evidence_checks(h, p, req)


def _post_evidence_checks(h, p: str, req: dict):
    if p == "/api/tension":
        if not isinstance(req.get("a"), dict) or not isinstance(req.get("b"), dict):
            return h._json({"error": "provide measurement objects 'a' and 'b'"}, 400)
        from harness.tension_ledger import bank_tension
        doc = bank_tension(req["a"], req["b"])
        return h._json(doc, 400 if "error" in doc else 200)
    if p == "/api/capability":
        endpoint = (req.get("endpoint") or "").strip()
        if not endpoint:
            return h._json({"error": "provide a non-empty 'endpoint'"}, 400)
        from harness.frontier import capability_probe
        doc = capability_probe(endpoint)
        if "error" not in doc:
            if isinstance(req.get("disk_gb"), (int, float)):
                doc["disk_gb"], doc["disk_gb_source"] = float(req["disk_gb"]), "declared by caller"
            _store_entity_tag("capability", doc)
        return h._json(doc)
    if p == "/api/retention":
        original = (req.get("original") or "").strip()
        if not original or not isinstance(req.get("passed"), bool):
            return h._json({"error": "provide 'original' (entity id) and boolean 'passed'"}, 400)
        from harness.retention import retention_record
        return h._json(retention_record(original, req["passed"], note=str(req.get("note", ""))))
    if p == "/api/explain":
        diff, explanation = req.get("diff") or "", req.get("explanation") or ""
        if not diff.strip() or not explanation.strip():
            return h._json({"error": "provide 'diff' and 'explanation'"}, 400)
        from harness.explanation_gate import explanation_receipt
        try:
            threshold = min(1.0, max(0.1, float(req.get("threshold", 0.6))))
        except (TypeError, ValueError):
            threshold = 0.6
        doc = explanation_receipt(diff, explanation, threshold=threshold, reviewer=str(req.get("reviewer", "")))
        _store_entity_tag("comprehension", doc)
        return h._json(doc)
    run_eid = (req.get("run_eid") or "").strip()
    review = req.get("review") if isinstance(req.get("review"), dict) else None
    files = req.get("reviewed_files")
    if not run_eid or review is None or not isinstance(files, list):
        return h._json({"error": "provide 'run_eid' (a banked agent-run entity), 'review' (the run's review doc, "
                                 "verified against the banked hash), and 'reviewed_files' (a list); an inline run "
                                 "doc is not accepted because an attestation binds to a run that actually happened"}, 400)
    from harness.attestation import attest_banked
    doc = attest_banked(run_eid, review, files, note=str(req.get("note", "")), reviewer=str(req.get("reviewer", "")))
    if "error" in doc:
        return h._json(doc, 409)
    _store_entity_tag("attestation", doc, project=str(req.get("project", "")))
    return h._json(doc)


def post_route_and_companion(h, p: str, *, route_request_fn, get_seat_fn, answer_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    prompt = (req.get("prompt") or "").strip()
    from harness.scaffold import scaffold_answer, scaffold_turn
    if p == "/api/route":
        endpoint = (req.get("endpoint") or "").strip()
        if not prompt or not endpoint:
            return h._json({"error": "provide non-empty 'prompt' and 'endpoint'"}, 400)
        model = req.get("model") or ""
        if not isinstance(model, str) or len(model.strip()) > 200:
            return h._json({"error": "'model' must be a string of at most 200 characters"}, 400)
        env = scaffold_turn(prompt)
        body, code = route_request_fn(prompt, endpoint, model=model.strip())
        if code == 200 and isinstance(body, dict):
            body["scaffold"] = scaffold_answer(
                str(body.get("text", "")), env,
                provenance={"endpoint": endpoint, "model_ref": str(body.get("model_ref") or endpoint)})
            from harness.usage_route import emit_route_usage
            body["usage_receipt_file"] = emit_route_usage(body, getattr(h, "run_root", None), prompt)
        return h._json(body, code)
    if not prompt:
        return h._json({"error": "provide a non-empty 'prompt'"}, 400)
    seat = get_seat_fn(h.serve_url)
    if seat is None:
        return h._json({"error": "companion seat unavailable"}, 503)
    env = scaffold_turn(prompt)
    body = answer_fn(seat, prompt, req.get("solution_sig", ""), effort=req.get("effort"))
    body["scaffold"] = scaffold_answer(
        str(body.get("text", "")), env,
        provenance={"endpoint": "companion", "model_ref": str(body.get("model_ref") or body.get("source") or "")})
    return h._json(body)


def post_workflow(h, *, resolve_root_fn, countersign_fn):
    req, bad = h._req_json()
    if bad:
        return bad
    goal, workflow = (req.get("goal") or "").strip(), (req.get("workflow") or "").strip()
    if not goal or not workflow:
        return h._json({"error": "provide 'workflow' and a non-empty 'goal'"}, 400)
    from harness.profiles import get_profile
    from harness.workflows import run_workflow
    profile = get_profile((req.get("profile") or "").strip()) or {}
    root, err = resolve_root_fn(req.get("root"), h.root)
    if err:
        return h._json({"error": err}, 400)
    try:
        doc = run_workflow(
            workflow, goal, (req.get("endpoint") or "serve").strip(), root=str(root),
            allow_write=bool(req.get("allow_write", False)), allow_exec=bool(req.get("allow_exec", False)),
            allow_mcp=bool(req.get("allow_mcp", False)), test_cmd=(req.get("test_cmd") or None),
            system=profile.get("system", ""), run_root=h.run_root,
            credential_bindings=getattr(h, "_gateway_bindings", None), authorized=True)
    except Exception as e:
        return h._json({"error": f"workflow failed: {type(e).__name__}: {e}"}, 502)
    doc["run_countersign"] = countersign_fn(doc)
    return h._json(doc)


def post_auth_and_keys(h, p: str):
    req, bad = h._req_json()
    if bad: return bad
    if p.startswith("/api/auth/"):
        from harness import oauth_service
        provider = (req.get("provider") or "").strip()
        if p == "/api/auth/login": out = oauth_service.begin(provider, callback_base=(req.get("callback_base") or None))
        elif p == "/api/auth/token": out = oauth_service.submit(provider, req.get("token") or "")
        elif p == "/api/auth/cancel": out = oauth_service.cancel(provider)
        else: out = oauth_service.sign_out(provider)
        return h._json(out, 200 if out.get("ok") else 400)
    if p == "/api/keychain/set":
        from harness.keychain_route import keychain_set_post; return h._json(*keychain_set_post(req))
    if p == "/api/keychain/delete":
        from harness.keychain_route import keychain_delete_post; return h._json(*keychain_delete_post(req, h.flywheel_home))
    from harness.bulletin_identity_route import bulletin_identity_create_post, bulletin_identity_register_post
    fn = bulletin_identity_create_post if p == "/api/bulletin-identity/create" else bulletin_identity_register_post
    return h._json(*fn(req, h.flywheel_home))

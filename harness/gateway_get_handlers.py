"""Extracted GET route handler bodies for harness/gateway.py."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, unquote_plus


def _qs_val(qs: str, key: str) -> str:
    for part in qs.split("&"):
        if part.startswith(key + "="):
            return part[len(key) + 1:]
    return ""


def _qs_int(qs: str, key: str, default: int) -> int:
    try:
        return int(_qs_val(qs, key))
    except ValueError:
        return default


def handle_discovery(h, p: str) -> bool:
    from harness.discovery_route import handle_discovery_get
    doc = handle_discovery_get(p)
    if doc is not None:
        h._raw(*doc)
        return True
    return False


def handle_operations(h, p: str, qs: str):
    from harness.gateway_operation_route import route_gateway_operation
    service, factory = h._operation_components()
    return h._operation_response(route_gateway_operation(
        "GET", p, query=qs, owner_ref=h.owner_ref, service=service, process_factory=factory))


def handle_models(h, qs: str):
    name = _qs_val(qs, "endpoint")
    if not name:
        return h._json({"error": "provide ?endpoint=NAME"}, 400)
    from harness.model_roster import list_models
    return h._json(list_models(name))


def handle_lanes_and_desktop(h, p: str, qs: str):
    from harness.lanes import lane_roster
    if p == "/api/lanes":
        return h._json(lane_roster(probe=("probe=true" in qs or "probe=1" in qs)))
    from harness.desktop_status import desktop_status
    return h._json(desktop_status(lane_roster(), startup_recovery=getattr(h, "startup_recovery", None)))


def handle_relay_run(h, p: str, qs: str, relay_call_fn):
    rid = parse_qs(qs).get("run_id", [""])[0]
    tool = "local_agent_status" if p.endswith("status") else "local_agent_result"
    return h._json(relay_call_fn(tool, {"run_id": rid}))


def handle_lessons(h, p: str):
    from harness.lesson_store import LessonStore
    store = LessonStore.load(Path(h.run_root) / "lessons.jsonl")
    if p == "/api/lessons":
        return h._json({"n": len(store), "improvement_feed": store.improvement_feed(), "verify": store.verify()})
    return h._json({"patterns": [item.to_dict() for item in store.patterns()]})


def handle_governance(h, p: str, qs: str):
    if p == "/api/governance/tiers":
        from harness.governance.tadr_tier import TADR_MODIFIERS, TADR_TIERS, T2_OVERRIDES, T3_OVERRIDES
        return h._json({
            "tiers": TADR_TIERS, "modifiers": sorted(TADR_MODIFIERS),
            "t2_overrides": sorted(T2_OVERRIDES), "t3_overrides": sorted(T3_OVERRIDES),
        })
    if p == "/api/governance/compliance":
        from harness.governance.control_baseline import check_compliance
        return h._json(check_compliance("T1").to_dict())
    from harness.governance.tadr_tier import classify
    params = parse_qs(qs) if qs else {}
    try:
        return h._json(classify(params.get("override", [])).to_dict())
    except ValueError as e:
        return h._json({"error": str(e)}, 400)


def handle_train_loop(h):
    from harness.train_surface import loop_status
    try:
        return h._json(loop_status())
    except Exception as e:
        return h._json({"error": f"{type(e).__name__}: {e}"}, 502)


def handle_typeface_get(h, p: str, qs: str):
    if p == "/api/typeface/gallery":
        limit = 60
        for part in qs.split("&"):
            if part.startswith("limit="):
                try:
                    limit = int(unquote_plus(part[6:]))
                except ValueError:
                    pass
        from harness.typeface_gallery import gallery
        return h._json(gallery(limit=limit))
    eid = ""
    for part in qs.split("&"):
        if part.startswith("eid="):
            eid = unquote_plus(part[4:])
    from harness.typeface_gallery import fetch_face
    out = fetch_face(eid)
    return h._json(out, 404 if "error" in out else 200)


def handle_frontier(h):
    from harness.frontier import frontier_table
    from harness.store import get_entity, query_entities
    probes, seen = [], set()
    for meta in query_entities(kind="capability"):
        e = get_entity(meta["eid"])
        if e and isinstance(e.get("data"), dict):
            ep = e["data"].get("endpoint", "")
            if ep and ep not in seen:
                seen.add(ep)
                probes.append(e["data"])
    return h._json(frontier_table(h.root, probes=probes))


def handle_query_views(h, p: str, qs: str):
    if p == "/api/retention":
        from harness.retention import retention_due
        days = 3.0
        for part in qs.split("&"):
            if part.startswith("days="):
                try:
                    days = max(0.0, float(part[5:]))
                except ValueError:
                    days = 3.0
        return h._json(retention_due(days=days))
    if p == "/api/comprehension":
        from harness.comprehension_ledger import comprehension_ledger
        project = None
        for part in qs.split("&"):
            if part.startswith("project="):
                project = unquote_plus(part[8:]) or None
        return h._json(comprehension_ledger(project=project))
    if p == "/api/feeds":
        from harness.live_feeds import live_feeds
        domain = None
        for part in qs.split("&"):
            if part.startswith("domain="):
                domain = unquote_plus(part[7:]) or None
        return h._json(live_feeds(domain=domain))
    from harness.knowledge_graph import gateway_graph
    budget, with_index, query = None, False, None
    for part in qs.split("&"):
        if part.startswith("budget="):
            try:
                budget = int(part[7:])
            except ValueError:
                budget = None
        if part == "index=true":
            with_index = True
        if part.startswith("q="):
            query = unquote_plus(part[2:])
    return h._json(gateway_graph(h.root, h.run_root, with_index=with_index, budget=budget, query=query))


def handle_receipts_proof(h, qs: str, ledger_fn):
    from harness.receipt_proof import route_payload
    led = ledger_fn(h.root, h.run_root)
    leaves = [e["sha256"] for e in led["envelopes"]]
    return h._json(*route_payload(_qs_val(qs, "leaf").strip(), leaves))


def handle_store_get(h, p: str, qs: str):
    if p == "/api/store":
        from harness.store import stats
        return h._json(stats())
    if p == "/api/store/verify":
        from harness.store import verify_chain, verify_records
        chain, records = verify_chain(), verify_records()
        return h._json({
            "schema": "flywheel.store-verify/v1",
            "ok": bool(chain.get("ok")) and bool(records.get("ok")),
            "chain": chain, "records": records,
            "note": "ok requires BOTH the ledger chain and the records it attests; a "
                    "tampered entity fails records even when the chain still verifies",
        })
    from harness.store import audit_tail
    return h._json({"schema": "flywheel.store-audit/v1", "entries": audit_tail(_qs_int(qs, "n", 50))})


def handle_misc_get(h, p: str, qs: str):
    if p == "/api/train/duel":
        from harness.train_surface import duel_summary; return h._json(duel_summary())
    if p == "/api/loops":
        from harness.loops import measure_all_loops; return h._json(measure_all_loops())
    if p == "/api/tension":
        from harness.tension_ledger import tension_ledger; return h._json(tension_ledger())
    if p == "/api/instruments":
        from harness.eval_engineering import instrument_register; return h._json(instrument_register())
    if p == "/api/academy":
        from harness.academy_pipeline import academy_curriculum; return h._json(academy_curriculum())
    if p == "/api/readiness":
        from harness.release_readiness import readiness_report; return h._json(readiness_report())
    if p == "/api/credo":
        from harness.credo import credo_doc; return h._json(credo_doc())
    if p == "/api/uplift":
        from harness.uplift_bench import bench_summary; return h._json(bench_summary(h.root))
    if p == "/api/profiles":
        from harness.profiles import profile_roster; return h._json(profile_roster())
    if p == "/api/workflows":
        from harness.workflows import workflow_roster; return h._json(workflow_roster(h.run_root))
    if p == "/api/workflow/run":
        from harness.workflows import workflow_run_detail; return h._json(workflow_run_detail(h.run_root, _qs_val(qs, "chain")))
    if p == "/api/science/runs":
        from harness.eval_store import science_runs; return h._json(science_runs(h.run_root, limit=_qs_int(qs, "limit", 20)))
    if p == "/api/science/run":
        from harness.eval_store import science_run_detail; return h._json(science_run_detail(h.run_root, _qs_val(qs, "chain")))
    if p == "/api/memory":
        from harness.memory_api import memory_stats; return h._json(memory_stats(h.run_root))
    if p == "/api/memory/list":
        from harness.memory_api import memory_list; return h._json(memory_list(h.run_root, limit=_qs_int(qs, "limit", 20)))
    return _handle_catalog_get(h, p)


def _handle_catalog_get(h, p: str):
    if p == "/api/plugins":
        from harness.plugins import plugin_roster; return h._json(plugin_roster())
    if p == "/api/parity":
        from harness.parity import parity_matrix; return h._json(parity_matrix())
    if p == "/api/projects":
        from harness.projects import project_roster; return h._json(project_roster())
    if p == "/api/marketplace":
        from harness.marketplace import marketplace_catalog; return h._json(marketplace_catalog())
    if p == "/api/auth":
        from harness import oauth_service; return h._json(oauth_service.auth_rows())
    if p == "/api/keychain":
        from harness.keychain_route import keychain_get; return h._json(keychain_get())
    if p == "/api/bulletin-identity":
        from harness.bulletin_identity_route import bulletin_identity_get; return h._json(*bulletin_identity_get())
    if p == "/api/credential-handles":
        from harness.credential_handle_route import credential_handle_get
        return h._json(*credential_handle_get(p, owner_ref=h.owner_ref, state_root=h.flywheel_home / "state"))
    if p == "/api/session-tokens":
        from harness.session_token_route import session_token_get
        return h._json(*session_token_get(owner_ref=h.owner_ref, token_store=h._session_tokens()))
    return h._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_REQUEST", "message": "plugin probe requires POST approval"}}, 405)

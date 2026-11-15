from __future__ import annotations

from types import SimpleNamespace

from canon.context_query import search
from canon.context_store import ContextStore


WORKSPACE = "test-workspace"
PROJECT = "test-project"


def _event(event_id: str, text: str) -> dict:
    return {
        "workspace_id": WORKSPACE,
        "project_id": PROJECT,
        "event": {
            "event_id": event_id,
            "source_app": "codex",
            "native_id": event_id,
            "session_id": "identifier-query-regression",
            "message_text": text,
            "sources": [{
                "source_id": "message",
                "source_kind": "prompt",
                "locator": f"turn:{event_id}",
                "extraction_status": "completed",
            }],
        },
    }


def _query(store: ContextStore, text: str) -> dict:
    return store.query(WORKSPACE, PROJECT, text, top_k=5, include_pending=False)


def _record(record_id: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=record_id,
        data={
            "text": text,
            "event_record_id": record_id,
            "claim_state": "reported_by_source",
        },
        provenance=SimpleNamespace(
            source_hash=f"sha256-{record_id}",
            harness="test",
            native_id=record_id,
            session_id="identifier-query-unit",
        ),
    )


def test_paper_id_query_ranks_exact_identifier_above_keyword_near_miss(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event(
        "near-miss",
        "API interface benchmark note for https://huggingface.co/papers/2609.13141.",
    ))
    store.ingest(_event(
        "intended",
        "Source record for https://arxiv.org/abs/2609.08861v1.",
    ))

    result = _query(store, "2609.08861 API interface benchmark")

    assert "2609.08861v1" in result["hits"][0]["excerpt"]
    assert "2609.13141" not in result["hits"][0]["excerpt"]
    assert result["coverage"]["method"] == "deterministic_identifier_keyword_overlap"
    assert result["coverage"]["identifier_query_count"] >= 1
    assert result["coverage"]["identifier_matching_records"] >= 1
    assert result["coverage"]["ranking"] == "identifier_overlap_then_keyword_overlap_then_record_id"
    assert result["coverage"]["explicit_version_policy"] == (
        "exact version identifiers rank only exact versions; keyword fallback may still return other versions"
    )


def test_base_paper_id_and_url_query_match_versioned_source(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event("intended-v1", "Read https://arxiv.org/abs/2609.08861v1."))
    store.ingest(_event("other-paper", "Read https://huggingface.co/papers/2609.13141."))

    base = _query(store, "2609.08861")
    url = _query(store, "https://arxiv.org/abs/2609.08861v1")

    assert "2609.08861v1" in base["hits"][0]["excerpt"]
    assert "2609.08861v1" in url["hits"][0]["excerpt"]


def test_explicit_version_query_prefers_matching_version(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event(
        "v1",
        "API interface benchmark source https://arxiv.org/abs/2609.08861v1.",
    ))
    store.ingest(_event("v2", "Revision source https://arxiv.org/abs/2609.08861v2."))

    result = _query(store, "2609.08861v2 API interface benchmark")

    assert "2609.08861v2" in result["hits"][0]["excerpt"]


def test_malformed_punctuation_id_does_not_match_shared_numeric_prefix(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event("intended-v1", "Read https://arxiv.org/abs/2609.08861v1."))

    result = _query(store, "2609,08861")

    assert result["hits"] == []
    assert result["status"] == "not_found_in_searched_sources"
    assert result["coverage"]["identifier_query_count"] == 0


def test_ordinary_numeric_keyword_queries_still_match_non_identifier_numbers(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    store.ingest(_event(
        "numeric-keywords",
        "The 186 run happened in 2026 with 32 workers.",
    ))

    assert "186 run" in _query(store, "186")["hits"][0]["excerpt"]
    assert "2026" in _query(store, "2026")["hits"][0]["excerpt"]
    assert "32 workers" in _query(store, "32")["hits"][0]["excerpt"]


def test_identifier_rank_beats_more_than_one_hundred_keyword_overlaps() -> None:
    keywords = [f"term{i}" for i in range(120)]
    result = search(
        [
            _record("keyword-heavy", " ".join(keywords) + " https://huggingface.co/papers/2609.13141"),
            _record("identifier-match", "Source record for https://arxiv.org/abs/2609.08861v1."),
        ],
        WORKSPACE,
        PROJECT,
        "2609.08861 " + " ".join(keywords),
        top_k=2,
        include_pending=False,
    )

    assert result["hits"][0]["record_id"] == "identifier-match"
    assert result["hits"][1]["record_id"] == "keyword-heavy"


def test_url_matching_normalizes_scheme_and_host_but_preserves_path_and_query_case() -> None:
    keywords = [f"word{i}" for i in range(20)]
    result = search(
        [
            _record("wrong-case-url", " ".join(keywords) + " https://example.test/papers/abc?Token=one"),
            _record("exact-url", "See https://example.test/Papers/ABC?Token=One"),
        ],
        WORKSPACE,
        PROJECT,
        "HTTPS://EXAMPLE.TEST/Papers/ABC?Token=One " + " ".join(keywords),
        top_k=2,
        include_pending=False,
    )

    assert result["hits"][0]["record_id"] == "exact-url"


def test_malformed_url_query_does_not_count_as_normalized_identifier() -> None:
    result = search(
        [_record("body", "Untrusted pasted text with ordinary searchable context.")],
        WORKSPACE,
        PROJECT,
        "Untrusted pasted text https://[oops",
        top_k=5,
        include_pending=False,
    )

    assert result["status"] == "found_in_searched_sources"
    assert result["hits"][0]["record_id"] == "body"
    assert result["coverage"]["identifier_query_count"] == 0
    assert result["coverage"]["malformed_url_count"] == 1


def test_malformed_urls_in_stored_body_do_not_break_search(tmp_path) -> None:
    ipv6_store = ContextStore(tmp_path / "ipv6.sqlite")
    ipv6_store.ingest(_event(
        "bad-ipv6-url",
        "Untrusted pasted text https://[oops with ordinary searchable context.",
    ))
    nfkc_store = ContextStore(tmp_path / "nfkc.sqlite")
    nfkc_store.ingest(_event(
        "bad-nfkc-url",
        "Unicode host paste https://example／test/path with another searchable note.",
    ))

    ipv6 = ipv6_store.query(WORKSPACE, PROJECT, "ordinary searchable context", top_k=5, include_pending=False)
    nfkc = nfkc_store.query(WORKSPACE, PROJECT, "another searchable note", top_k=5, include_pending=False)

    assert "https://[oops" in ipv6["hits"][0]["excerpt"]
    assert "https://example／test/path" in nfkc["hits"][0]["excerpt"]
    assert ipv6["coverage"]["malformed_url_count"] == 1
    assert nfkc["coverage"]["malformed_url_count"] == 1


def test_invalid_nfkc_url_query_does_not_count_as_normalized_identifier() -> None:
    result = search(
        [_record("body", "Unicode host paste remains searchable by nearby words.")],
        WORKSPACE,
        PROJECT,
        "Unicode host paste https://example／test/path",
        top_k=5,
        include_pending=False,
    )

    assert result["status"] == "found_in_searched_sources"
    assert result["coverage"]["identifier_query_count"] == 0
    assert result["coverage"]["malformed_url_count"] == 1

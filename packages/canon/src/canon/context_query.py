"""Bounded deterministic lookup, with explicit extraction and search coverage.

What a query returns passes through the secret scrubber. Each excerpt is
scrubbed whole and then cut, so a secret that straddles the cut is still
recognised, and each pending reference is scrubbed before it is listed.
Transcript locators are counted, not listed: canon never reads a transcript,
and its path names the client's project directory and often the account
(D-166).
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from .context_records import LIMITS, required_text
from .context_related import related_events
from .workspace.scrub import scrub

EXCERPT_CHARS = 2000
_DONE = frozenset({"completed", "extracted", "reviewed"})

_ARXIV_ID = re.compile(r"(?<![\w.])(\d{4}\.\d{4,5})(v\d+)?(?!\w)", re.IGNORECASE)
_COMPOUND_ID = re.compile(r"(?<!\w)([a-z0-9]+(?:[._:-][a-z0-9]+){1,})(?!\w)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<>)\"']+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}\"'"
_IDENTIFIER_SCORE_STEP = 10_000


def pending_sources(records):
    pending = []
    for rec in records:
        for item in _pending_items(rec):
            if item.get("source_kind") == "transcript_locator":
                continue
            ref = str(item.get("ref", item.get("locator", "unknown")))
            status = str(item.get("extraction_status", "pending_extraction"))
            pending.append({"event_record_id": rec.id, "ref": scrub(ref).text[:1024],
                            "status": scrub(status).text[:120]})
    return pending


def unlisted_locators(records) -> int:
    """How many pending transcript locators a query counts but does not list."""
    return sum(1 for rec in records for item in _pending_items(rec)
               if item.get("source_kind") == "transcript_locator")


def _pending_items(rec) -> list:
    if rec.data.get("record_role") != "event":
        return []
    return [item for item in rec.data.get("attachments", []) + rec.data.get("sources", [])
            if item.get("extraction_status", "pending_extraction") not in _DONE]


def search(records, workspace, project, query, top_k, include_pending,
           include_related=False, related_limit=5, exclude_answers=False):
    required_text(query, "query", 200_000)
    if type(top_k) is not int or not 0 <= top_k <= 20:
        raise ValueError("top_k must be an integer between 0 and 20")
    if type(include_pending) is not bool:
        raise ValueError("include_pending must be boolean")
    if type(include_related) is not bool:
        raise ValueError("include_related must be boolean")
    if type(related_limit) is not int or not 0 <= related_limit <= 20:
        raise ValueError("related_limit must be an integer between 0 and 20")
    query_identifiers = _query_identifiers(query)
    tokens = _keyword_tokens(query)
    matches = []
    identifier_matches = 0
    malformed_url_count = _malformed_url_count(query)
    for rec in records:
        body = str(rec.data["text"])
        malformed_url_count += _malformed_url_count(body)
        identifier_score = len(query_identifiers & _body_identifiers(body))
        keyword_score = len(tokens & _keyword_tokens(body))
        score = identifier_score * _IDENTIFIER_SCORE_STEP + keyword_score
        if score:
            identifier_matches += 1 if identifier_score else 0
            matches.append((identifier_score, keyword_score, score, rec, body))
    roles = _event_roles(records)
    matches, left_out = _drop_answers(matches, roles) if exclude_answers else (matches, None)
    matches.sort(key=lambda row: (-row[0], -row[1], row[3].id))
    hits = [hit(rec, text, score, workspace, project,
                roles.get(rec.data["event_record_id"], "user"))
            for _identifier_score, _keyword_score, score, rec, text in matches[:top_k]]
    pending = pending_sources(records)
    result = _base_result(workspace, project, _query_status(matches, pending), hits, pending,
                          include_pending, records, matches, query_identifiers,
                          identifier_matches, malformed_url_count)
    result["coverage"]["transcript_locators_not_listed"] = unlisted_locators(records)
    if left_out is not None:
        result["coverage"]["answers_left_out"] = left_out
    if include_related:
        related, coverage = related_events(records, hits, workspace, project, related_limit)
        result["related_events"] = related
        result["coverage"].update(coverage)
        result["does_not_prove"] = result["does_not_prove"] + [
            "related source references do not prove truth, currentness, or supersession"]
    return result


def _event_roles(records) -> dict:
    """The message role of each event, which its derived records share."""
    return {rec.id: rec.data.get("message_role", "user") for rec in records
            if rec.data.get("record_role") == "event"}


def _drop_answers(matches, roles):
    """Matches outside assistant events, and how many were left out."""
    kept = [row for row in matches
            if roles.get(row[3].data["event_record_id"]) != "assistant"]
    return kept, len(matches) - len(kept)


def _query_status(matches, pending):
    if matches:
        return "found_in_searched_sources"
    return "pending_extraction" if pending else "not_found_in_searched_sources"


def _base_result(workspace, project, result_status, hits, pending, include_pending,
                 records, matches, query_identifiers, identifier_matches,
                 malformed_url_count):
    return {"schema": "canon.context-query/v1", "status": result_status, "hits": hits,
            "pending_extraction": pending[:20] if include_pending else [],
            "coverage": _coverage(workspace, project, records, matches, hits, pending,
                                  include_pending, query_identifiers,
                                  identifier_matches, malformed_url_count),
            "does_not_prove": list(LIMITS)}


def _coverage(workspace, project, records, matches, hits, pending, include_pending,
              query_identifiers, identifier_matches, malformed_url_count):
    return {"workspace_id": workspace, "project_id": project,
            "records_searched": len(records), "matching_records": len(matches),
            "hits_omitted": max(0, len(matches) - len(hits)),
            "pending_count": len(pending),
            "pending_returned": min(20, len(pending)) if include_pending else 0,
            "method": "deterministic_identifier_keyword_overlap",
            "identifier_query_count": len(query_identifiers),
            "identifier_matching_records": identifier_matches,
            "ranking": "identifier_overlap_then_keyword_overlap_then_record_id",
            "explicit_version_policy": "exact version identifiers rank only exact versions; keyword fallback may still return other versions",
            "url_normalization": "scheme_host_lowercase_path_query_preserved",
            "malformed_url_count": malformed_url_count,
            "historical_completeness": "unknown",
            "source_freshness": "not_checked",
            "supersession_resolution": "not_implemented"}


def hit(rec, text, score, workspace, project, message_role="user"):
    clean = scrub(text).text
    return {"record_id": rec.id, "workspace_id": workspace, "project_id": project,
            "message_role": message_role,
            "excerpt": clean[:EXCERPT_CHARS], "excerpt_truncated": len(clean) > EXCERPT_CHARS,
            "claim_state": rec.data.get("claim_state"), "score": score,
            "citation": {"record_key": "workspace/" + rec.id,
                         "event_record_id": rec.data["event_record_id"],
                         "source_hash": rec.provenance.source_hash,
                         "source_app": rec.provenance.harness,
                         "native_id": rec.provenance.native_id,
                         "session_id": rec.provenance.session_id}}


def _query_identifiers(text):
    return _identifiers(text, include_version_base=False)


def _body_identifiers(text):
    return _identifiers(text, include_version_base=True)


def _identifiers(text, include_version_base):
    terms = set()
    for match in _URL.finditer(text):
        normalized = _normalize_url(match.group(0))
        if normalized is not None:
            terms.add(f"url:{normalized}")
    for match in _ARXIV_ID.finditer(text):
        base = match.group(1).casefold()
        version = match.group(2).casefold() if match.group(2) else None
        if version:
            terms.add(f"arxiv-version:{base}{version}")
            if include_version_base:
                terms.add(f"arxiv-base:{base}")
        else:
            terms.add(f"arxiv-base:{base}")
    for match in _COMPOUND_ID.finditer(text):
        token = match.group(1).strip("._:-").casefold()
        if any(ch.isdigit() for ch in token) and not _is_arxiv_id(token):
            terms.add(f"compound:{token}")
    return terms


def _normalize_url(raw_url):
    cleaned = raw_url.rstrip(_TRAILING_URL_PUNCTUATION)
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme.casefold(), _normalize_netloc(parts.netloc),
                       parts.path, parts.query, parts.fragment))


def _normalize_netloc(netloc):
    auth, separator, hostport = netloc.rpartition("@")
    prefix = auth + separator if separator else ""
    if hostport.startswith("["):
        host, close, port = hostport.partition("]")
        return prefix + host.casefold() + close + port
    host, colon, port = hostport.partition(":")
    return prefix + host.casefold() + colon + port


def _is_arxiv_id(token):
    return re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", token) is not None


def _keyword_tokens(text):
    chars = list(text)
    for start, end in _identifier_spans(text):
        for index in range(start, end):
            chars[index] = " "
    return set(re.findall(r"\w+", "".join(chars).casefold()))


def _identifier_spans(text):
    spans = [match.span() for match in _URL.finditer(text)
             if _normalize_url(match.group(0)) is not None]
    spans.extend(match.span() for match in _ARXIV_ID.finditer(text))
    for match in _COMPOUND_ID.finditer(text):
        token = match.group(1).strip("._:-").casefold()
        if any(ch.isdigit() for ch in token) and not _is_arxiv_id(token):
            spans.append(match.span())
    return spans


def _malformed_url_count(text):
    return sum(1 for match in _URL.finditer(text)
               if _normalize_url(match.group(0)) is None)

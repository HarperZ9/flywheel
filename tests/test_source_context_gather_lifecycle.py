import json
import os

import pytest

from harness.source_context_gather import GatherPathAdapter
from harness.source_context_route import admit_flywheel_corpus, source_context_post
from harness.source_context_windows import SourceContextWindowsGuard
from tests.test_source_context_route import NOW, OWNER

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows guard contract")


def test_real_gather_path_lifecycle_keeps_exact_selected_text(tmp_path):
    context = pytest.importorskip("gather.context")
    item = pytest.importorskip("gather.item")
    store = pytest.importorskip("gather.store")
    corpus_path = tmp_path / "corpus"
    corpus = store.Corpus(str(corpus_path), fsync=False)
    corpus.add([item.make_item(kind="document", id="alpha",
        title="Alpha", text="0123456789DECISION-FACT-ALPHA\nnaïve café",
        source="docs", ref="alpha", method="file-read", fetched_at=1.0),
        item.make_item(kind="document", id="distractor", title="Distractor",
        text="DISTRACTOR-UNSELECTED", source="docs", ref="distractor",
        method="file-read", fetched_at=1.0)])

    adapter = GatherPathAdapter(guard_cls=SourceContextWindowsGuard)
    inspected = adapter.inspect(corpus_path, max_rows=2)
    row_ref = next(row["row_ref"] for row in inspected["rows"]
                   if row["id"] == "alpha")
    selected = adapter.select(corpus_path, [{"row_ref": row_ref,
        "start": 10, "limit": 25}],
        expected_corpus_digest=corpus.digest().seal)

    assert inspected["schema"] == "gather.readable-corpus/v1"
    assert selected["schema"] == "gather.readable-context/v1"
    assert selected["selections"][0]["text"] == "DECISION-FACT-ALPHA\nnaïve"
    assert "DISTRACTOR-UNSELECTED" not in repr(selected)
    assert context.inspect_corpus is not None


def test_replaced_admitted_corpus_rejects_before_actual_gather_read(tmp_path, monkeypatch):
    context = pytest.importorskip("gather.context")
    item = pytest.importorskip("gather.item")
    store = pytest.importorskip("gather.store")
    corpus_path = tmp_path / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    original = store.Corpus(str(corpus_path), fsync=False)
    original.add([item.make_item(kind="document", id="alpha", title="Alpha",
        text="ORIGINAL-APPROVED-CORPUS", source="docs", ref="alpha",
        method="file-read", fetched_at=1.0)])
    admit_flywheel_corpus(tmp_path, OWNER, "demo", "tiny", clock=lambda: NOW)
    corpus_path.rename(tmp_path / "admitted-original")
    replacement = store.Corpus(str(corpus_path), fsync=False)
    replacement.add([item.make_item(kind="document", id="replacement",
        title="Replacement", text="UNADMITTED-CORPUS-CANARY",
        source="docs", ref="replacement", method="file-read", fetched_at=2.0)])
    observed = []
    original_inspect = context.inspect_corpus
    def inspect_observed(path, **caps):
        result = original_inspect(path, **caps)
        observed.append(json.dumps(result))
        return result
    monkeypatch.setattr(context, "inspect_corpus", inspect_observed)

    body, status = source_context_post("/api/source-context/inspect",
        json.dumps({"schema": "flywheel.source-context-request/v1",
            "root_mode": "flywheel_corpus", "profile": "demo",
            "corpus": "tiny", "max_rows": 1}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)

    assert status == 409
    assert body["error"]["code"] == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert observed == []

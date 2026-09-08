import os

import pytest

from harness.source_context_gather import GatherPathAdapter
from harness.source_context_windows import SourceContextWindowsGuard

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

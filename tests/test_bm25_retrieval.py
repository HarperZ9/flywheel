"""Local retrieval with provenance (landscape import 9, scoped honestly):
zero-dep BM25 over chunked repo files, every hit carrying file, line, and
the chunk's content hash — a snippet the model cites is re-checkable
against the exact text retrieved. Vendor token-savings claims from the
source tool do not travel here; this module's numbers are its own."""

from harness.bm25_retrieval import build_index, search


def _repo(tmp_path):
    (tmp_path / "billing.py").write_text(
        "def compute_invoice(items, tax_rate):\n"
        "    subtotal = sum(i.price for i in items)\n"
        "    return subtotal * (1 + tax_rate)\n",
        encoding="utf-8")
    (tmp_path / "auth.py").write_text(
        "def verify_token(token):\n"
        "    return token.startswith('valid-')\n",
        encoding="utf-8")
    return tmp_path


def test_the_right_chunk_wins_with_provenance(tmp_path):
    idx = build_index(_repo(tmp_path))
    hits = search(idx, "invoice tax subtotal", k=2)
    assert hits[0]["path"] == "billing.py"
    assert hits[0]["line"] == 1
    assert len(hits[0]["sha256"]) == 64
    assert "compute_invoice" in hits[0]["excerpt"]
    assert hits[0]["score"] > 0


def test_deterministic_ranking(tmp_path):
    idx = build_index(_repo(tmp_path))
    a = search(idx, "token", k=2)
    b = search(idx, "token", k=2)
    assert a == b
    assert a[0]["path"] == "auth.py"


def test_no_match_is_an_empty_list_not_an_invention(tmp_path):
    idx = build_index(_repo(tmp_path))
    assert search(idx, "quantum entanglement carburetor") == []


def test_caps_are_counted(tmp_path):
    _repo(tmp_path)  # billing.py ~122 bytes, auth.py ~67 bytes
    (tmp_path / "big.md").write_text("x" * 500, encoding="utf-8")
    idx = build_index(tmp_path, max_bytes=200)
    assert idx["skipped"] == 1
    assert idx["files"] == 2

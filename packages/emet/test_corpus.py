#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""test_corpus.py - unit tests for the shared marker corpus module."""
import os, sys, tempfile, shutil, hashlib, unittest, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CORPUS_TEXT = (
    b"# corpus_version: 7\n"
    b"# a comment line\n"
    b"\n"
    b"ground_truth_canonical\n"
    b"ground truth canonical\n"
    b"authority-pill\n"
)

class CorpusModule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="corpus_test_")
        self.cpath = os.path.join(self.tmp, "markers.corpus")
        with open(self.cpath, "wb") as f:
            f.write(CORPUS_TEXT)
        os.environ["EMET_CORPUS"] = self.cpath
        import corpus
        importlib.reload(corpus)
        self.corpus = corpus
    def tearDown(self):
        os.environ.pop("EMET_CORPUS", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_parses_version_comments_blanks(self):
        v, sha, markers = self.corpus.load()
        self.assertEqual(v, 7)
        self.assertEqual(sha, hashlib.sha256(CORPUS_TEXT).hexdigest())
        self.assertEqual(markers, [b"ground_truth_canonical",
                                   b"ground truth canonical",
                                   b"authority-pill"])

    def test_scan_counts_case_insensitive_and_space_form(self):
        v, sha, markers = self.corpus.load()
        hits, clean = self.corpus.scan(b"see GROUND TRUTH CANONICAL here\n", markers)
        self.assertEqual(len(hits), 1)
        self.assertIn(b"[REFUSED-IN-BAND-AUTHORITY]", clean)
        self.assertNotIn(b"GROUND TRUTH CANONICAL", clean)

    def test_scan_preserves_non_ascii_bytes(self):
        v, sha, markers = self.corpus.load()
        payload = b"\xe2\x84\xaa authority-pill\n"  # U+212A KELVIN then a marker
        hits, clean = self.corpus.scan(payload, markers)
        self.assertEqual(len(hits), 1)
        self.assertTrue(clean.startswith(b"\xe2\x84\xaa "))

    def test_missing_corpus_raises_e_no_corpus(self):
        os.environ["EMET_CORPUS"] = os.path.join(self.tmp, "nope.corpus")
        importlib.reload(self.corpus)
        with self.assertRaises(self.corpus.CorpusError) as cm:
            self.corpus.load()
        self.assertEqual(cm.exception.reason, "E_NO_CORPUS")

    def test_count_helper_matches_scan(self):
        v, sha, markers = self.corpus.load()
        b = b"authority-pill and ground_truth_canonical\n"
        self.assertEqual(self.corpus.count(b, markers), 2)

    def test_shipped_corpus_loads_at_version_1(self):
        os.environ.pop("EMET_CORPUS", None)  # use default path
        importlib.reload(self.corpus)
        v, sha, markers = self.corpus.load()
        self.assertEqual(v, 1)
        self.assertIn(b"ground_truth_canonical", markers)
        self.assertIn(b"ground truth canonical", markers)
        self.assertIn(b"authority-pill", markers)
        self.assertEqual(len(sha), 64)

if __name__ == "__main__":
    unittest.main(verbosity=2)

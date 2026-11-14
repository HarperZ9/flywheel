"""2.x reads and verifies every record a 1.x release wrote (docs/VERSIONING.md).

The fixture set holds one record set per 1.x minor, written by the code of
that release from PyPI (tests/fixtures/compat/records-1.x/README.md). The
check is scripts/verify_compat_records.py, the same script a clean install
runs.

The second half is the false-success controls. A check that answered MATCH to
everything would pass the first half, so each control is a function that
takes the reader as an argument and is run twice: against the real reader,
which must let nothing through, and against a reader that cannot fail, which
must be caught.
"""
import json
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_compat_records as V  # noqa: E402

RELEASES = [p.name for p in V.record_folders()]
OLD, NEW = "does_" + "not_prove", "scope"


def _minor(version):
    return tuple(int(x) for x in version.split(".")[:2])


def _always_match(files, release=""):
    return V.MATCH, ""


def _rewitness_only(files, release=""):
    """The re-witness of the gate and nothing else: a real but narrow reader."""
    try:
        raw = files[V.ENVELOPE]
        V._once("rewitness", raw, lambda: V._rewitness(raw))
    except V._Stop as stop:
        return stop.args[0], stop.args[1]
    return V.MATCH, ""


def _record(release):
    return V.read_record(V.DEFAULT_ROOT / release)


# --- every 1.x record verifies -----------------------------------------------

def test_the_set_holds_a_record_from_every_1x_minor():
    assert {_minor(v) for v in RELEASES} == {(1, n) for n in range(10)}
    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    listed = re.findall(r"^## (1\.\d+)\.\d+", log, re.M)
    assert listed
    assert {tuple(int(x) for x in v.split(".")) for v in listed} <= {
        _minor(v) for v in RELEASES}


@pytest.mark.parametrize("release", RELEASES)
def test_a_record_written_by_a_1x_release_verifies(release):
    assert V.verify_record(_record(release), release) == (V.MATCH, "")


@pytest.mark.parametrize("release", RELEASES)
def test_a_1x_receipt_keeps_its_own_vocabulary(release):
    body = json.loads(_record(release)[V.RECEIPT])
    assert body["schema"] == "flywheel.receipt/v4"
    assert body["harness_version"] == release
    assert OLD in body and NEW not in body
    assert all(code.startswith("NOT_PROVES_") for code in body[OLD])


def test_the_committed_bytes_are_the_bytes_the_releases_wrote():
    assert V.sums_problems() == []
    sums = (V.DEFAULT_ROOT / V.SUMS).read_text(encoding="utf-8").splitlines()
    assert len(sums) == len(RELEASES) * len(V.FILES)


def test_the_command_exits_zero_on_the_set_and_one_on_an_altered_copy(tmp_path, capsys):
    assert V.main([str(V.DEFAULT_ROOT)]) == 0
    assert capsys.readouterr().out.count(V.MATCH) == len(RELEASES)
    copy = tmp_path / "records"
    shutil.copytree(V.DEFAULT_ROOT, copy)
    target = copy / "1.6.0" / V.RECEIPT
    target.write_bytes(target.read_bytes().replace(b'"objective": "7"', b'"objective": "6"'))
    assert V.main([str(copy)]) == 1
    out = capsys.readouterr().out
    assert "DRIFT  1.6.0" in out and f"1.6.0/{V.RECEIPT}: bytes differ" in out


def test_verifying_the_whole_set_stays_under_its_time_budget():
    """Budget: 1 second for all eleven record sets, imports excluded. The
    control beside it: the same run with 0.1 s added per record set must miss
    the budget, so the assertion can fail."""
    def run(delay):
        V._SEEN.clear()
        start = time.perf_counter()
        for release in RELEASES:
            time.sleep(delay)
            assert V.verify_record(_record(release), release)[0] == V.MATCH
        return time.perf_counter() - start
    assert run(0) < 1.0
    assert run(0.1) > 1.0


# --- false-success controls --------------------------------------------------

def test_no_single_flipped_byte_reads_match():
    tried, passed = V.flipped_byte_control(V.verify_record)
    assert tried == sum(len(data) for release in RELEASES
                        for data in _record(release).values())
    assert passed == []


def test_a_reader_that_cannot_fail_is_caught_by_the_flipped_byte_control():
    tried, passed = V.flipped_byte_control(_always_match)
    assert tried > 50_000 and len(passed) == tried


def test_a_narrow_reader_lets_altered_records_through():
    """The re-witness alone reads only the candidate, the verdict and the
    oracle hash. It is honest and still reads MATCH on altered records, which
    is why the record check does more than re-witness."""
    files = _record("1.9.0")
    assert _rewitness_only(files)[0] == V.MATCH
    edits = [(name, V.flip(files[name], len(files[name]) // 2))
             for name in (V.REPORT, V.RECEIPT)]
    old, new = b'"prompt_hash": "ad0c', b'"prompt_hash": "ad0d'
    assert old in files[V.ENVELOPE]
    edits.append((V.ENVELOPE, files[V.ENVELOPE].replace(old, new)))
    for name, data in edits:
        altered = {**files, name: data}
        assert _rewitness_only(altered)[0] == V.MATCH
        assert V.verify_record(altered, "1.9.0")[0] in (V.DRIFT, V.FAIL)
    seen = files[V.ENVELOPE].replace(b'"verdict": "PASS"', b'"verdict": "FAIL"')
    assert _rewitness_only({**files, V.ENVELOPE: seen})[0] == V.DRIFT


def test_a_record_carrying_both_names_is_refused():
    assert V.both_names_control(V.verify_record) == []
    files = _record("1.9.0")
    body = json.loads(files[V.RECEIPT])
    body[NEW] = list(body[OLD])
    altered = (json.dumps(body, indent=2, sort_keys=True) + "\n").encode()
    verdict, reason = V.verify_record({**files, V.RECEIPT: altered}, "1.9.0")
    assert verdict == V.FAIL and "both field names" in reason


def test_the_product_reader_refuses_both_names_without_the_script():
    from harness.receipt import Receipt
    from harness.receipt_fields import ReceiptError
    body = json.loads(_record("1.0.0")[V.RECEIPT])
    assert Receipt.from_dict(body).claim_sha256() == body["claim_sha256"]
    with pytest.raises(ReceiptError):
        Receipt.from_dict({**body, NEW: list(body[OLD])})


def test_a_reader_that_cannot_fail_is_caught_by_the_both_names_control():
    assert V.both_names_control(_always_match) == RELEASES


@pytest.mark.parametrize("name, old, new, verdict", [
    (V.ENVELOPE, b'"verdict": "PASS"', b'"verdict": "FAIL"', V.DRIFT),
    (V.ENVELOPE, b'"seed": 0', b'"seed": 4', V.DRIFT),
    (V.ENVELOPE, b'"chain": []', b'"chaim": []', V.FAIL),
    (V.REPORT, b'"rewitness": "MATCH"', b'"rewitness": "DRIFT"', V.DRIFT),
    (V.REPORT, b'"n_pass": 1', b'"n_pass": 4', V.DRIFT),
    (V.RECEIPT, b'"objective": "7"', b'"objective": "6"', V.DRIFT),
    (V.RECEIPT, b'"held_out_agreement": "NOT_RUN"', b'"held_out_agreement": "AGREE"', V.FAIL),
    (V.RECEIPT, b'"schema": "flywheel.receipt/v4"', b'"schema": "flywheel.receipt/v5"', V.FAIL),
    (V.RECEIPT, b'    "NOT_PROVES_NOVELTY",\n', b'', V.FAIL),
    (V.RECEIPT, b'"tokens_out": 0', b'"tokens_out": 9', V.DRIFT),
])
def test_a_meaningful_edit_is_named(name, old, new, verdict):
    files = _record("1.3.4")
    assert old in files[name]
    altered = {**files, name: files[name].replace(old, new)}
    got, reason = V.verify_record(altered, "1.3.4")
    assert got == verdict and name in reason


def test_a_missing_file_fails():
    files = _record("1.0.0")
    del files[V.REPORT]
    assert V.verify_record(files, "1.0.0") == (V.FAIL, f"missing {V.REPORT}")


def test_harness_version_is_bound_by_the_set_and_not_by_the_receipt():
    """A finding the control made: harness_version sits outside both receipt
    digests in v3, v4 and v5, so the receipt alone cannot show the field was
    edited. The set binds it to the release folder and to SHA256SUMS."""
    files = _record("1.2.1")
    old, new = b'"harness_version": "1.2.1"', b'"harness_version": "1.2.0"'
    assert old in files[V.RECEIPT]
    altered = {**files, V.RECEIPT: files[V.RECEIPT].replace(old, new)}
    assert V.verify_record(altered, "1.2.1")[0] == V.DRIFT
    assert V.verify_record(altered)[0] == V.MATCH


def test_the_versioning_page_states_the_promise_and_the_exception():
    page = (ROOT / "docs" / "VERSIONING.md").read_text(encoding="utf-8")
    flat = " ".join(page.split())
    assert "any 1.x release reads and verifies with every 2.x release" in flat
    assert "tests/fixtures/compat/records-1.x" in flat
    assert "### The 2.0.0 exception (2026-11-14)" in page
    assert "MIGRATING-2.0.md" in page and "flywheel-verify<2" in page
    assert "security fixes for 90 days after 2.0.0" in flat
    assert "for the whole major release line" not in flat

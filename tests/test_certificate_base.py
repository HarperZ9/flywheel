"""The CertificateOracle: a checker that reads data and never runs it.

This is the choice that makes the whole chain safe to hand to a stranger. A
construction certificate is a data structure, and validating it is arithmetic
over that structure. Nothing is compiled, imported, exec'd, or spawned, so
`flywheel verify` on an untrusted bundle is not remote code execution.

Two further properties the base enforces so no subclass has to remember them:

  - Declared parameters outside the criterion's scope bounds are refused BEFORE
    dispatch, and yield UNVERIFIABLE with a reason rather than a FAIL. A
    candidate is not wrong for being out of scope; the check simply does not
    apply, and saying FAIL there would teach a policy to avoid legal regions.
  - Every result carries a coverage block naming what the check did NOT cover.
    A receipt that only reports its proof is how a true explanation becomes a
    fake passport.
"""
import pytest

from harness.certificates.base import (
    CertificateOracle, Coverage, CertificateError, parse_certificate,
)
from harness.verdict import Verdict, Attribution, UnverifiableReason


class _SumOracle(CertificateOracle):
    """Toy checker: the certificate must declare n and a list of n integers
    summing to `target`. Exact integer arithmetic, no execution."""

    oracle_type = "sum_certificate"
    family = "toy_sum"
    scope_bounds = {"n_max": 8}

    def check(self, cert: dict) -> tuple[bool, str, Coverage]:
        items = cert["items"]
        target = cert["target"]
        total = sum(items)
        cov = Coverage(predicate_exact=True, search_space_enumerated=True,
                       enumerated_fraction="1", stop_reason="complete",
                       guarantee_weakens_above=None)
        if total != target:
            return False, f"sum {total} != target {target}", cov
        return True, f"sum {total} equals target", cov

    def declared_parameters(self, cert: dict) -> dict:
        return {"n": len(cert["items"])}

    def objective_of(self, cert: dict) -> str:
        return str(sum(cert["items"]))


def _cert(items=(1, 2, 3), target=6) -> str:
    import json
    return json.dumps({"items": list(items), "target": target})


# --- the load-bearing property ----------------------------------------------

def test_the_base_never_executes_candidate_code():
    """Structural, not aspirational: the module must not import any execution
    primitive. A checker that can spawn is a checker a bundle can weaponize."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "harness" / "certificates" / "base.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    banned = {"subprocess", "socket", "ctypes", "pickle", "shutil", "importlib"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name) and node.id in ("eval", "exec", "compile"):
            found.add(node.id)
    assert not (found & (banned | {"eval", "exec", "compile"})), found


# --- verdicts ----------------------------------------------------------------

def test_a_valid_certificate_passes_and_carries_its_objective():
    r = _SumOracle().verify(_cert(), None)
    assert r.verdict() == "PASS"
    assert r.objective == "6"
    assert r.attribution is Attribution.CANDIDATE


def test_an_invalid_certificate_fails_with_the_reason_in_the_excerpt():
    r = _SumOracle().verify(_cert(target=999), None)
    assert r.verdict() == "FAIL"
    assert "999" in r.stdout_excerpt


def test_unparseable_input_is_a_candidate_fail_not_an_unverifiable():
    # The candidate emitted something that is not a certificate. That is the
    # candidate's error, so it earns a FAIL rather than muddying the record.
    r = _SumOracle().verify("this is not json", None)
    assert r.verdict() == "FAIL"
    assert r.attribution is Attribution.CANDIDATE


def test_a_certificate_missing_a_required_field_is_a_candidate_fail():
    r = _SumOracle().verify('{"items": [1,2]}', None)
    assert r.verdict() == "FAIL"
    assert r.attribution is Attribution.CANDIDATE


# --- scope: out of bounds is UNVERIFIABLE, never FAIL ------------------------

def test_out_of_scope_parameters_are_refused_before_dispatch():
    r = _SumOracle().verify(_cert(items=tuple(range(20)), target=190), None)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == UnverifiableReason.OUT_OF_SCOPE.value


def test_out_of_scope_does_not_run_the_check_at_all():
    class _Counting(_SumOracle):
        calls = 0

        def check(self, cert):
            type(self).calls += 1
            return super().check(cert)

    o = _Counting()
    o.verify(_cert(items=tuple(range(20)), target=190), None)
    assert _Counting.calls == 0


def test_out_of_scope_is_not_attributed_to_the_candidate():
    # A candidate is not wrong for being outside the criterion's declared scope.
    # Scoring FAIL there would teach a policy to avoid legal regions.
    r = _SumOracle().verify(_cert(items=tuple(range(20)), target=190), None)
    assert r.attribution is not Attribution.CANDIDATE


def test_a_certificate_at_exactly_the_bound_is_in_scope():
    r = _SumOracle().verify(_cert(items=tuple(range(8)), target=28), None)
    assert r.verdict() == "PASS"


# --- coverage ----------------------------------------------------------------

def test_every_result_carries_a_coverage_block():
    r = _SumOracle().verify(_cert(), None)
    assert r.coverage["predicate_exact"] is True
    assert r.coverage["stop_reason"] == "complete"


def test_coverage_names_what_the_check_does_not_prove():
    r = _SumOracle().verify(_cert(), None)
    assert isinstance(r.does_not_prove, list)
    assert "NOT_PROVES_NOVELTY" in r.does_not_prove


def test_a_bounded_predicate_says_so_in_does_not_prove():
    class _Bounded(_SumOracle):
        def check(self, cert):
            cov = Coverage(predicate_exact=False, search_space_enumerated=False,
                           enumerated_fraction="1/1000", stop_reason="budget",
                           guarantee_weakens_above="n>4")
            return True, "sampled", cov

    r = _Bounded().verify(_cert(), None)
    assert "NOT_PROVES_EXACTNESS" in r.does_not_prove
    assert r.coverage["guarantee_weakens_above"] == "n>4"


def test_coverage_rejects_a_float_fraction():
    # No floats in a hashed field.
    with pytest.raises(CertificateError):
        Coverage(predicate_exact=True, search_space_enumerated=True,
                 enumerated_fraction=0.5, stop_reason="complete",
                 guarantee_weakens_above=None)


# --- determinism and hashing --------------------------------------------------

def test_the_same_certificate_yields_the_same_output_hash():
    a = _SumOracle().verify(_cert(), None)
    b = _SumOracle().verify(_cert(), None)
    assert a.output_hash == b.output_hash


def test_semantically_identical_certificates_with_different_key_order_agree():
    import json
    one = json.dumps({"items": [1, 2, 3], "target": 6})
    two = json.dumps({"target": 6, "items": [1, 2, 3]})
    assert (_SumOracle().verify(one, None).output_hash
            == _SumOracle().verify(two, None).output_hash)


def test_a_different_certificate_yields_a_different_output_hash():
    a = _SumOracle().verify(_cert(), None)
    b = _SumOracle().verify(_cert(items=(2, 2, 2)), None)
    assert a.output_hash != b.output_hash


def test_raw_output_hash_is_present_and_is_not_the_output_hash():
    r = _SumOracle().verify(_cert(), None)
    assert len(r.raw_stdout_sha256) == 64
    assert r.raw_stdout_sha256 != r.output_hash


# --- parse helper -------------------------------------------------------------

def test_parse_certificate_rejects_a_non_object():
    ok, cert, why = parse_certificate("[1,2,3]")
    assert ok is False
    assert "object" in why


def test_parse_certificate_rejects_trailing_garbage():
    ok, cert, why = parse_certificate('{"a":1} and then some')
    assert ok is False


def test_parse_certificate_accepts_a_clean_object():
    ok, cert, why = parse_certificate('{"a": 1}')
    assert ok is True
    assert cert == {"a": 1}

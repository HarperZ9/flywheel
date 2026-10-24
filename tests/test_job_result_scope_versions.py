"""A PySyft result receipt names its scope list per version; both verify.

The kept fixture in tests/fixtures/pysyft_receipt is a v1 receipt signed over
the older list under the older name. A v2 body names `scope`. A body that
carries both names drifts.
"""
from __future__ import annotations

from harness import job_result_receipt as jr
from harness.job_result_verify import DRIFT, MATCH, verify
from harness.scope import LEGACY_SCOPE_KEY
from tests.test_job_result_receipt import _resign, case  # noqa: F401  (fixture)


def _as_v2(c):
    """The kept v1 body rewritten in the v2 vocabulary and resigned."""
    body = c["env"]["body"]
    body.pop(LEGACY_SCOPE_KEY)
    body.update(schema=jr.SCHEMA, scope=list(jr.SCOPE))
    c["env"], c["kw"]["public_key_hex"] = _resign(body)


def test_the_kept_fixture_is_v1_and_verifies_with_the_older_name(case):
    body = case["env"]["body"]
    assert body["schema"] == jr.SCHEMA_V1 and tuple(body[LEGACY_SCOPE_KEY]) == jr.SCOPE_V1
    assert verify(case["env"], **case["kw"])["verdict"] == MATCH


def test_a_v2_body_names_scope_and_verifies(case):
    _as_v2(case)
    assert verify(case["env"], **case["kw"])["verdict"] == MATCH


def test_a_body_carrying_both_names_drifts(case):
    _as_v2(case)
    case["env"]["body"][LEGACY_SCOPE_KEY] = list(jr.SCOPE_V1)
    case["env"], case["kw"]["public_key_hex"] = _resign(case["env"]["body"])
    r = verify(case["env"], **case["kw"])
    assert r["verdict"] == DRIFT and "schema_or_scope" in r["failed"]

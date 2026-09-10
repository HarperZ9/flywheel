from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path

import pytest

from harness import gateway
from harness.gateway_custody import is_private
from harness.route_inventory import gateway_routes
from tests.enterprise_envs.package_helpers import add_product_src
from tests.enterprise_envs.test_service_desk_review_report import (
    _artifact_dir,
    _close_target_incident,
    _rehash_after_snapshot,
)


PATH = "/api/enterprise-envs/service-desk-incident/review"


def _post(run_root: Path, body: dict):
    from harness.enterprise_envs.service_desk_review_route import (
        service_desk_review_post,
    )

    return service_desk_review_post(
        PATH, json.dumps(body).encode("utf-8"), run_root=run_root)


def test_route_reviews_service_desk_artifacts_without_local_path_leak(tmp_path):
    add_product_src()
    artifact_dir = _artifact_dir(tmp_path / "run-root")
    ref = artifact_dir.relative_to(tmp_path / "run-root").as_posix()

    body, code = _post(tmp_path / "run-root", {"artifact_dir_ref": ref})

    assert code == 200
    assert body["schema"] == "flywheel.enterprise-env-review/v1"
    assert body["environment_id"] == "service-desk-incident/v1"
    assert body["artifact_dir_ref"] == ref
    report = body["report"]
    assert report["schema"] == "service-desk-incident-env-review/v1"
    assert report["verification"]["observed_state"] == "pass"
    assert report["verification"]["artifact_dir_ref"] == ref
    assert "artifact_dir" not in report
    assert "artifact_dir" not in report["verification"]
    assert str(tmp_path) not in json.dumps(body)


def test_route_preserves_rehashed_false_success_as_semantic_failure(tmp_path):
    add_product_src()
    run_root = tmp_path / "run-root"
    artifact_dir = _artifact_dir(run_root)
    false_success = run_root / "self-consistent-false-success"
    shutil.copytree(artifact_dir, false_success)
    _close_target_incident(false_success / "domain-state-after.json")
    _rehash_after_snapshot(false_success)

    body, code = _post(run_root, {
        "artifact_dir_ref": false_success.relative_to(run_root).as_posix(),
    })

    assert code == 200
    report = body["report"]
    assert report["claimed_outcome"]["all_recorded_cases_passed"] is True
    assert report["verification"]["observed_state"] == "fail"
    assert report["verification"]["failure_codes"] == ["target_incident_not_open"]
    assert report["evidence_layers"]["source_integrity"]["observed_state"] == "pass"
    assert report["evidence_layers"]["synthetic_task_check"]["observed_state"] == "fail"


def test_route_rejects_unsafe_refs_before_product_review(tmp_path, monkeypatch):
    calls = []

    def load_product():
        calls.append("called")
        raise AssertionError("product must not load for an unsafe path")

    monkeypatch.setattr(
        "harness.enterprise_envs.compat.load_service_desk_product",
        load_product,
    )

    body, code = _post(tmp_path, {"artifact_dir_ref": "C:/Users/private/run"})

    assert code == 400
    assert body["error"]["code"] == "INVALID_REF"
    assert calls == []


def test_route_reports_missing_and_old_products_as_unavailable(tmp_path, monkeypatch):
    from harness.enterprise_envs.compat import EnterpriseEnvironmentProductMissing

    artifact_dir = tmp_path / "run-root" / "artifact"
    artifact_dir.mkdir(parents=True)

    def missing_product():
        raise EnterpriseEnvironmentProductMissing(
            "service-desk-incident/v1", "flywheel-env-service-desk-incident")

    monkeypatch.setattr(
        "harness.enterprise_envs.compat.load_service_desk_product",
        missing_product,
    )
    body, code = _post(tmp_path / "run-root", {"artifact_dir_ref": "artifact"})
    assert code == 503
    assert body["error"]["code"] == "PRODUCT_UNAVAILABLE"

    class OldProduct:
        @staticmethod
        def review_artifacts(_artifact_dir):
            return {
                "schema": "service-desk-incident-env-review/v1",
                "verification": {
                    "schema": "service-desk-incident-env-artifact-verification/v1",
                    "observed_state": "pass",
                    "failure_codes": [],
                },
                "claimed_outcome": {},
                "recomputed_outcome": {},
                "evidence_layers": {},
                "limits": [],
            }

    monkeypatch.setattr(
        "harness.enterprise_envs.compat.load_service_desk_product",
        lambda: OldProduct,
    )
    body, code = _post(tmp_path / "run-root", {"artifact_dir_ref": "artifact"})
    assert code == 503
    assert body["error"]["code"] == "PRODUCT_UPGRADE_REQUIRED"


def test_route_rejects_symlink_artifacts_before_product_scan(tmp_path):
    run_root = tmp_path / "run-root"
    artifact_dir = run_root / "artifact"
    outside = tmp_path / "outside.txt"
    artifact_dir.mkdir(parents=True)
    outside.write_text("outside", encoding="utf-8")
    link = artifact_dir / "outside-link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not permit symlink creation")

    body, code = _post(run_root, {"artifact_dir_ref": "artifact"})

    assert code == 422
    assert body["error"]["code"] == "UNSAFE_ARTIFACT_TREE"


class _Headers:
    def __init__(self, size: str):
        self.size = size

    def get(self, key, default=None):
        return self.size if key == "Content-Length" else default


def test_gateway_dispatches_private_service_desk_review_route(tmp_path, monkeypatch):
    raw = b'{"artifact_dir_ref":"artifact"}'
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = PATH
    handler.run_root = tmp_path
    handler.headers = _Headers(str(len(raw)))
    handler.rfile = io.BytesIO(raw)
    sent = {}
    seen = []

    monkeypatch.setattr(
        "harness.enterprise_envs.service_desk_review_route.service_desk_review_post",
        lambda path, body, run_root: (
            seen.append((path, body, run_root))
            or ({"schema": "route-witness/v1"}, 209)
        ),
    )
    handler._json = lambda body, code=200: sent.update(body=body, code=code)
    handler._post()

    assert sent == {"body": {"schema": "route-witness/v1"}, "code": 209}
    assert seen == [(PATH, raw, tmp_path)]
    assert is_private(PATH)
    routes = {route.path: route for route in gateway_routes()}
    assert routes[PATH].methods == ("POST",)
    assert routes[PATH].description == "review ServiceDesk incident evidence"

"""Opt-in, frozen-manifest local study. Default preflight performs no model I/O."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import sys
import time

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from harness.bulletin_model_budget import CampaignBudget
from harness.bulletin_model_campaign import run_campaign
from harness.bulletin_model_exchange import PrivateExchange
from harness.bulletin_model_fixture import OwnedBulletinFixture
from harness.bulletin_model_manifest import read_manifest, verify_sources
from harness.bulletin_model_native import NativeCoordinator, NativeLaunch
from harness.bulletin_model_review import native_reviewer, review_prefix
from harness.bulletin_model_reconcile import reconcile_generation_accounting
from harness.bulletin_model_worker import supervise_generation
from harness.evidence_json import canonical_bytes


def execute(manifest, raw_manifest, manifest_sha, out):
    """Only call after source/conformance review and prospective root admission."""
    if manifest["execution_admitted"] is not True:
        raise ValueError("execution_not_admitted")
    paths = {key: Path(value) for key, value in manifest["paths"].items()}
    started = time.monotonic()
    with ExitStack() as stack:
        root = stack.enter_context(PrivateExchange.create(out))
        def area(path):
            return stack.enter_context(PrivateExchange.create(path))
        control, invocations = area(out / "control"), area(out / "invocations")
        fixture_area, native_area = area(out / "fixtures"), area(out / "native")
        blind_area = area(out / "blind-review")
        root.put("manifest.json", raw_manifest, max_bytes=65536)
        budget = CampaignBudget(control, manifest["run_id"])
        current = {"native": None, "active_started": None}
        invocation_stores = {}

        def accounting(label):
            refs = budget.ledger_refs()
            control.put(label + "-inventory.json", canonical_bytes({"ledger_refs": refs,
                "invocations": {stage: {"identity": store.identity.to_json_dict(), "path": str(store.path)}
                    for stage, store in invocation_stores.items()}}), max_bytes=65536)
            report = reconcile_generation_accounting(run_id=manifest["run_id"], ledger=control,
                ledger_refs=refs, invocations=invocation_stores)
            control.put(label + "-accounting.json", canonical_bytes(report), max_bytes=262144)
            return report

        def invoke(**kwargs):
            remaining = 3600 - (time.monotonic() - started)
            if current["native"] is not None:
                # Native dispatch closes its child normally before the claim phase.
                # The campaign owns the episode clock independently of that handle.
                remaining = min(remaining, 240 + current["native"].review_elapsed -
                                (time.monotonic() - current["active_started"]))
            if remaining <= 0:
                raise TimeoutError("campaign_or_episode_deadline")
            timeout = min(60, remaining)
            store = area(invocations.path / kwargs["stage_id"])
            invocation_stores[kwargs["stage_id"]] = store
            request = {"schema_version": 1, "run_id": manifest["run_id"],
                       "profile": manifest["profile"], "timeout_seconds": timeout, **kwargs}
            return supervise_generation(request, exchange=store,
                reservation=budget.reservation_evidence(kwargs["reservation_id"]), ledger=control,
                repository=REPOSITORY, python_executable=paths["python"], timeout_seconds=timeout)

        @contextmanager
        def fixture_factory(slot):
            setup_started = time.monotonic()
            frozen = manifest["slots"][int(slot["slot_id"][1:]) - 1]
            spec = {"schema": "flywheel.bulletin-actor-fixture-input/v1",
                "run_id": manifest["run_id"], "slot_id": slot["slot_id"],
                "expected_source_commit": manifest["bulletin_source_commit"], "room": frozen["room"],
                "source_payload": frozen["source_payload"], "lifetime_seconds": 600}
            if "decoy_payload" in frozen:
                spec["decoy_payload"] = frozen["decoy_payload"]
            slot_store = area(fixture_area.path / slot["slot_id"])
            with OwnedBulletinFixture.start(slot=slot_store, spec=spec, repository=REPOSITORY,
                    bulletin=paths["bulletin_source"], dependencies=paths["bulletin_dependencies"],
                    node_executable=paths["node"], python_executable=paths["python"]) as fixture:
                ipc = area(native_area.path / slot["slot_id"])
                reviewer_store = area(control.path / slot["slot_id"])
                remaining = 120 - (time.monotonic() - setup_started)
                if remaining <= 0:
                    raise TimeoutError("fixture_setup_deadline")
                launch = NativeLaunch(dart=paths["dart"], flutter_snapshot=paths["flutter_snapshot"],
                    flutter_packages=paths["flutter_packages"], desktop_root=REPOSITORY / "desktop",
                    fixture_config=fixture.config_path, fixture_config_sha256=fixture.config_sha,
                    manifest_sha256=manifest_sha, run_id=manifest["run_id"], slot_id=slot["slot_id"],
                    room=fixture.room, parent_ids=tuple(fixture.parent_ids),
                    request_id=f'{manifest["run_id"]}-{slot["slot_id"]}-reply',
                    gateway_origin=fixture.config["base_url"], bulletin_origin=fixture.ready["base"],
                    setup_seconds=remaining, env={key: os.environ[key] for key in (
                        "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "PATHEXT", "LOCALAPPDATA", "APPDATA", "USERPROFILE",
                        "PROGRAMFILES", "PROGRAMFILES(X86)") if key in os.environ})
                native = NativeCoordinator(ipc, launch=launch, reviewer=native_reviewer(reviewer_store))
                try:
                    native.prestart()
                    current["native"] = native
                    current["active_started"] = time.monotonic()
                    fixture.dispatch = native.dispatch
                    fixture.bind_model_output = native.bind_model_output
                    control.put(slot["slot_id"] + "-setup.json", canonical_bytes({
                        "setup_seconds": time.monotonic() - setup_started,
                        "config_sha256": fixture.config_sha, "board_origin": fixture.ready["base"],
                        "gateway_origin": fixture.config["base_url"]}), max_bytes=8192)
                    yield fixture
                finally:
                    current["native"] = None
                    native.close()

        def prefix(rows):
            report = accounting("prefix")
            if report["reconciled"] is not True:
                budget.stop()
                raise ValueError("prefix_accounting_incomplete")
            gate = review_prefix(rows, blind_store=blind_area, control_store=control)
            gate["attempts_reconciled"] = report["reconciled"]
            return gate

        result = run_campaign(budget=budget, store=control, invoke=invoke,
            fixture_factory=fixture_factory,
            prefix_review=prefix,
            final_review=lambda rows: review_prefix(rows, blind_store=area(out / "blind-final"),
                control_store=area(control.path / "final-review"), continuation=False))
        report = accounting("final")
        result["accounting"] = report
        if report["reconciled"] is not True:
            result["failure"] = result["failure"] or "final_accounting_incomplete"
            budget.stop()
        root.put("final-result.json", canonical_bytes(result), max_bytes=2097152)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest, raw = read_manifest(args.manifest, args.manifest_sha256)
        verify_sources(manifest, REPOSITORY)
        if not args.execute:
            print("source_preflight_passed; no endpoint or fixture calls")
            return 0
        if args.out is None:
            raise ValueError("fresh_private_output_required")
        result = execute(manifest, raw, args.manifest_sha256, args.out)
        print("campaign_records_written; inspect private outcome and coverage")
        return 0 if result["failure"] is None else 2
    except Exception:
        print("bulletin_model_study_incomplete", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

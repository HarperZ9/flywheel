import copy
import json

from harness import gateway
from harness.live_screen_gateway_contract import validate_model_delivery
from harness.live_screen_gateway_mount import live_screen_post
from tests.test_live_screen_provider_delivery import (
    OWNER,
    SECRET,
    _FakeOpener,
    _approved_final,
    _bind_openai,
    _delivery_operation,
    _handler,
    _open_started_session,
)


def _deliver(tmp_path, monkeypatch, *, max_age_ms=60_000):
    session_id = _open_started_session(tmp_path)
    credential_ref = _bind_openai(tmp_path)
    monkeypatch.setattr("harness.keychain.resolve_credential",
                        lambda slot: SECRET if slot == "OPENAI_API_KEY" else "")
    operation = {**_delivery_operation(session_id, credential_ref),
                 "max_age_ms": max_age_ms}
    raw = _approved_final(tmp_path, "live_screen.deliver", operation, "deliver-1")
    h, sent = _handler(tmp_path, raw)
    h.provider_opener = _FakeOpener()
    live_screen_post(
        h, f"/api/live-screen/sessions/{session_id}/sources/display%3Aprimary/deliver",
        now_ns=1_200_000_000)
    assert sent["code"] == 200, json.dumps(sent["body"], sort_keys=True)
    return session_id, gateway._Handler.live_screen_manager, gateway._Handler.live_screen_scheduler, sent["body"]["receipt"]


def _content(receipt, **override):
    part = {
        "kind": "screen_frame",
        "frame": receipt["frame"],
        "model_route": receipt["model_route"],
        "model": receipt["model"],
        "delivery_ref": receipt["delivery_ref"],
        "delivery_receipt_sha256": receipt["delivery_receipt_sha256"],
    }
    part.update(override)
    return {"session_ref": "studio-screen-1", "instrument_ref": "screen",
            "latest_frame_ref": "display:primary:1",
            "model_delivery": {"parts": [part]}}


def test_screen_frame_model_delivery_rejects_bogus_delivery_metadata(tmp_path):
    session_id = _open_started_session(tmp_path)
    manager = gateway._Handler.live_screen_manager
    scheduler = gateway._Handler.live_screen_scheduler
    frame = manager.latest_frame(session_id, "display:primary", owner_ref=OWNER,
                                 now_ns=1_200_000_000)

    result = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content={"session_ref": "studio-screen-1", "instrument_ref": "screen",
                 "model_delivery": {"parts": [{
                     "kind": "screen_frame",
                     "frame": frame.identity(),
                     "model_route": "bogus_route",
                     "model": "bogus-model",
                     "delivery_ref": "dlv_" + "0" * 32,
                     "delivery_receipt_sha256": "1" * 64,
                 }]}},
        now_ns=1_200_000_000)

    assert result == {"validated": False, "status": "delivery_receipt_unverified"}


def test_screen_frame_model_delivery_validates_exact_bound_record(tmp_path, monkeypatch):
    _session_id, manager, scheduler, receipt = _deliver(tmp_path, monkeypatch)

    valid = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content=_content(receipt), now_ns=1_200_000_000)
    assert valid == {"validated": True, "status": "validated"}

    wrong_model = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content=_content(receipt, model="gpt-bogus"), now_ns=1_200_000_000)
    assert wrong_model == {"validated": False, "status": "delivery_receipt_mismatch"}

    wrong_frame = copy.deepcopy(receipt["frame"])
    wrong_frame["frame_sha256"] = "0" * 64
    wrong_frame_result = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content=_content(receipt, frame=wrong_frame), now_ns=1_200_000_000)
    assert wrong_frame_result == {
        "validated": False, "status": "delivery_receipt_mismatch"}

    wrong_owner = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref="owner_" + "b" * 32,
        content=_content(receipt), now_ns=1_200_000_000)
    assert wrong_owner == {"validated": False, "status": "delivery_receipt_unverified"}

    manager._delivery_records[receipt["delivery_ref"]] = {
        **manager._delivery_records[receipt["delivery_ref"]],
        "stale": True,
    }
    stale = validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content=_content(receipt), now_ns=1_200_000_000)
    assert stale == {"validated": False, "status": "delivery_receipt_stale"}


def test_frame_only_delivery_remains_allowed_for_direct_instrument_paths(tmp_path):
    session_id = _open_started_session(tmp_path)
    manager = gateway._Handler.live_screen_manager
    scheduler = gateway._Handler.live_screen_scheduler
    frame = manager.latest_frame(session_id, "display:primary", owner_ref=OWNER,
                                 now_ns=1_200_000_000)
    content = {"session_ref": "studio-screen-1", "instrument_ref": "screen",
               "model_delivery": {"parts": [{"kind": "image",
                                              "frame": copy.deepcopy(frame.identity())}]}}

    assert validate_model_delivery(
        manager=manager, scheduler=scheduler, owner_ref=OWNER,
        content=content, now_ns=1_200_000_000) == {
            "validated": True, "status": "validated"}

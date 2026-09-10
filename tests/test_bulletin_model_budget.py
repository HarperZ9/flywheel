"""Durability, nonrefundable reservations and a prospective prefix gate."""
import pytest

from harness.bulletin_model_budget import CampaignBudget, BudgetError, generation_plan
from harness.bulletin_model_exchange import PrivateExchange, ExchangeError


def test_exchange_is_exclusive_bounded_and_rejects_replay(tmp_path):
    root = tmp_path / "run"
    with PrivateExchange.create(root) as store:
        assert store.put("record.json", b'{"x":1}', max_bytes=30)
        assert store.read("record.json", max_bytes=30) == b'{"x":1}'
        with pytest.raises(ExchangeError):
            store.put("record.json", b'{"x":1}', max_bytes=30)
        with pytest.raises(ExchangeError):
            store.read("record.json", max_bytes=2)
        for name in ("../escape", "Record.json", "a:b", "/absolute", "a/b", "CON"):
            with pytest.raises(ExchangeError):
                store.put(name, b"x", max_bytes=2)
    with pytest.raises(ExchangeError):
        PrivateExchange.create(root)


def test_child_attachment_requires_parent_pinned_identity(tmp_path):
    with PrivateExchange.create(tmp_path / "one") as parent:
        with PrivateExchange.attach(tmp_path / "one", expected=parent.identity) as child:
            child.put("child.json", b"{}", max_bytes=2)
            assert parent.read("child.json", max_bytes=2) == b"{}"
        with PrivateExchange.create(tmp_path / "other") as other:
            with pytest.raises(ExchangeError):
                PrivateExchange.attach(tmp_path / "other", expected=parent.identity)


def test_relative_root_is_not_created(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ExchangeError):
        PrivateExchange.create(Path("relative"))
    assert not (tmp_path / "relative").exists()


def test_reservation_proof_names_exact_durable_record(tmp_path):
    import json
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        reservation = budget.reserve("readiness", 32)
        proof = budget.reservation_evidence(reservation)
        assert set(proof) == {"record_name", "sha256"}
        record = json.loads(store.read(proof["record_name"], max_bytes=32768, expected_sha256=proof["sha256"]))
        assert record["kind"] == "generation_reserved" and record["max_tokens"] == 32
        assert record["reservation_id"] == reservation
        assert store.path == tmp_path / "run"


def test_full_and_prefix_caps_are_not_extra_pilots(tmp_path):
    plan = generation_plan()
    assert len(plan) == 38 and sum(row["max_tokens"] for row in plan) == 18720
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        for row in plan[:14]:
            reservation = budget.reserve(row["stage_id"], row["max_tokens"])
            budget.finish(reservation, "response_received")
        with pytest.raises(BudgetError):
            budget.reserve(plan[14]["stage_id"], 512)
        budget.admit_continuation("a" * 64)
        for row in plan[14:]:
            reservation = budget.reserve(row["stage_id"], row["max_tokens"])
            budget.finish(reservation, "response_received")
        assert budget.summary()["reserved_generations"] == 38
        with pytest.raises(BudgetError):
            budget.reserve(plan[-1]["stage_id"], 512)


def test_incomplete_call_consumes_reservation_and_blocks_later_io(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        budget.reserve("readiness", 32)
        with pytest.raises(BudgetError):
            budget.reserve("smoke", 256)
        assert budget.summary()["reserved_generations"] == 1
        assert budget.summary()["completed_generations"] is None


def test_readiness_smoke_and_phase_order_cannot_be_skipped(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        for stage in ("smoke", "s01-p1", "s01-p2"):
            with pytest.raises(BudgetError):
                budget.reserve(stage, 32)
        budget.finish(budget.reserve("readiness", 32), "response_received")
        with pytest.raises(BudgetError):
            budget.reserve("s01-p1", 512)
        budget.finish(budget.reserve("smoke", 256), "response_received")
        with pytest.raises(BudgetError):
            budget.reserve("s01-p2", 512)


def test_sink_failure_is_sticky_and_does_not_refund(tmp_path, monkeypatch):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        original = store.put
        monkeypatch.setattr(store, "put", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
        with pytest.raises(BudgetError):
            budget.reserve("readiness", 32)
        monkeypatch.setattr(store, "put", original)
        with pytest.raises(BudgetError):
            budget.reserve("smoke", 256)
        assert budget.summary()["failed"]


def test_single_write_is_reserved_before_dispatch_and_never_reused(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        with pytest.raises(BudgetError):
            budget.reserve_write("s01", "b" * 64)
        for row in generation_plan()[:4]:
            reservation = budget.reserve(row["stage_id"], row["max_tokens"])
            budget.finish(reservation, "response_received")
        permit = budget.reserve_write("s01", "b" * 64)
        assert permit["operation_sha256"] == "b" * 64
        with pytest.raises(BudgetError):
            budget.reserve_write("s01", "b" * 64)
        assert budget.summary()["reserved_writes"] == 1


@pytest.mark.parametrize("tokens", [True, -1, 0, 33, 1.2])
def test_invalid_output_limit_never_reserves(tmp_path, tokens):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "campaign")
        with pytest.raises(BudgetError):
            budget.reserve("readiness", tokens)
        assert budget.summary()["reserved_generations"] == 0

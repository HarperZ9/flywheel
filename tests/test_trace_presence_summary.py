"""I17: the presence prompt shows what the operation does, built from the
plan, grant or settings behind the digest, never from the caller: counts per
store, the session and client, whole-custody wording, and an export's
resolved destination and redaction mode."""
import pytest

from delete_fixtures import OWNER, SESSION, plant_trace, plant_turn
from harness.trace_delete_plan import make_plan
from harness.trace_export_dest import create_grant
from harness.trace_presence import PresenceError
from harness.trace_presence_summary import describe, export_summary
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    with using(StreamTestProvider()):
        yield home


def test_a_delete_prompt_counts_stores_and_says_when_it_is_everything(home):
    refs = [plant_trace(home, operation=f"op_{i:032x}") for i in range(2)]
    plan = make_plan(home, OWNER, {"trace_refs": refs})
    text = describe(home, OWNER, "delete_apply", plan["plan_digest"])
    assert text.startswith(f"Delete {len(plan['entries'])} items (")
    assert ": 2" in text and "every item you hold in" in text
    assert plan["plan_digest"] in text
    one = make_plan(home, OWNER, {"trace_refs": refs[:1]})
    assert "every item" not in describe(home, OWNER, "delete_apply", one["plan_digest"])


def test_a_session_delete_names_the_session_and_client(home):
    plant_turn(home)
    plan = make_plan(home, OWNER, {"session": {"client": "claude-code",
                                               "session_id": SESSION}})
    text = describe(home, OWNER, "delete_apply", plan["plan_digest"])
    assert f"Whole session {SESSION} of claude-code" in text
    assert "Clients: claude-code" in text


def test_an_export_prompt_names_the_resolved_destination_and_redaction(home, tmp_path):
    out = tmp_path / "exports" / ".." / "exports" / "copy"
    grant = create_grant(home, OWNER, out, {"redact": False})
    text = describe(home, OWNER, "export", grant["export_digest"])
    assert str((tmp_path / "exports" / "copy").resolve()) in text
    assert "NOT redacted" in text
    assert "credentials redacted" in export_summary(out, {})
    assert "as one .zip file" in export_summary(out, {"zip": True})


def test_an_unknown_digest_is_refused_rather_than_shown_as_a_prefix(home):
    for kind in ("delete_apply", "export", "retention_apply", "capture_settings"):
        with pytest.raises(PresenceError) as refused:
            describe(home, OWNER, kind, "a" * 64)
        assert refused.value.code == "PRESENCE_UNDESCRIBED"


def test_the_cli_delete_prompt_is_the_plan_summary(home, monkeypatch, capsys):
    from harness import trace_cli
    from harness import trace_presence_verifiers as verifiers
    from harness import trace_witness
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    seen = []

    class Recorder:
        name = "none"

        def ask(self, summary):
            seen.append(summary)
            return True
    monkeypatch.setattr(verifiers, "verifier_for", lambda *a, **k: Recorder())
    ref = plant_trace(home)
    plan = make_plan(home, OWNER, {"trace_refs": [ref]})
    trace_cli.main(["delete", "--apply", "--plan-digest", plan["plan_digest"]])
    assert seen and seen[0].startswith("Delete ") and "every item you hold in" in seen[0]

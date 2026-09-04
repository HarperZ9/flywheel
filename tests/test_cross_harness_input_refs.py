"""The manifest and the workspace builder must read a reference the same way."""
import pytest

from harness.cross_harness_artifacts import create_attempt_workspace
from harness.cross_harness_input_refs import (
    REPO_RELATIVE, classify_reference, is_typed, partition_inputs,
)
from harness.cross_harness_manifest import _input_hashes


def test_a_bare_path_is_returned_for_the_caller_to_check_its_own_way():
    assert classify_reference("harness/lanes.py") == (REPO_RELATIVE, "harness/lanes.py")
    assert is_typed("harness/lanes.py") is False
    # Nothing is validated here, because the two callers check different things:
    # one copies the file, the other only hashes it.
    assert classify_reference("../escape") == (REPO_RELATIVE, "../escape")


def test_each_scheme_is_recognised_and_an_unknown_one_is_refused():
    for scheme in ("workspace", "external", "operator"):
        assert classify_reference(f"{scheme}://public/mneme") == (scheme, "public/mneme")
        assert is_typed(f"{scheme}://public/mneme") is True
    with pytest.raises(ValueError, match="typed reference invalid"):
        classify_reference("bogus://public/mneme")


@pytest.mark.parametrize("payload", ["", " leading", "/absolute", "\\absolute", "C:/drive",
                                     "../escape", "nested/../escape", "back\\slash"])
def test_a_typed_payload_carrying_an_escape_is_refused(payload):
    with pytest.raises(ValueError, match="typed reference invalid"):
        classify_reference(f"workspace://{payload}")


def test_inputs_split_into_what_a_workspace_can_hold_and_what_it_cannot():
    provisioned, unprovisioned = partition_inputs(
        ["harness/lanes.py", "workspace://public/mneme", "operator://opencode-installation-root"])
    assert provisioned == ["harness/lanes.py"]
    assert [row["scheme"] for row in unprovisioned] == ["workspace", "operator"]
    assert unprovisioned[0] == {"reference": "workspace://public/mneme",
                                "scheme": "workspace", "payload": "public/mneme"}


def test_a_pilot_task_may_not_declare_material_the_workspace_cannot_hold():
    # A task with a registered oracle checker is scored against a sealed
    # workspace, so a reference the workspace cannot hold makes the score
    # unreadable. The manifest enforced this before; it still does.
    with pytest.raises(ValueError, match="typed reference invalid"):
        partition_inputs(["workspace://public/mneme"], pilot=True)
    assert partition_inputs(["harness/lanes.py"], pilot=True) == (["harness/lanes.py"], [])


def test_both_halves_now_agree_on_the_same_reference(tmp_path):
    """The seam this module closes, stated as a test.

    _input_hashes accepted a typed reference and recorded no hash for it.
    create_attempt_workspace rejected the same string, because a scheme carries
    a colon and a colon is also how a Windows drive letter is written. Fifty of
    the seventy attempts in the 2026-09-03 head-to-head were discarded there,
    before any provider was called.
    """
    source, attempt = tmp_path / "source", tmp_path / "run" / "attempt"
    kept = source / "fixtures" / "facts.json"
    kept.parent.mkdir(parents=True)
    kept.write_text("{}", encoding="utf-8")
    declared = ["fixtures/facts.json", "workspace://public/mneme"]

    hashes = _input_hashes(source, declared, False)
    assert list(hashes) == ["fixtures/facts.json"]

    workspace, observed = create_attempt_workspace(source, declared, hashes, attempt)
    assert observed == hashes
    # Declared and not provisioned. The typed reference is not copied in, and
    # the attempt is no longer thrown away for having named it.
    assert not (workspace / "public").exists()

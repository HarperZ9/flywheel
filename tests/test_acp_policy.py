"""The grant boundary: what a delegated agent is allowed to do, and the record."""
import pytest

from harness.acp_policy import (AllowAll, CANCELLED, DenyAll, OutsideRoot,
                                SELECTED, WorkspacePolicy)

OPTIONS = [{"optionId": "yes", "name": "Allow", "kind": "allow_once"},
           {"optionId": "always", "name": "Always", "kind": "allow_always"},
           {"optionId": "no", "name": "Reject", "kind": "reject_once"}]


def ask(**extra):
    return dict({"sessionId": "s", "title": "Run a command",
                 "options": OPTIONS}, **extra)


def test_the_default_policy_refuses_and_advertises_that_it_refuses():
    policy = DenyAll()
    assert policy.reads is False
    assert policy.writes is False


def test_a_denied_permission_picks_the_agents_own_reject_option():
    policy = DenyAll()
    answer = policy.permission(ask())
    assert answer["outcome"] == {"outcome": SELECTED, "optionId": "no"}


def test_a_denial_with_no_reject_option_offered_cancels_instead_of_inventing_one():
    policy = DenyAll()
    answer = policy.permission(ask(options=[OPTIONS[0]]))
    assert answer["outcome"] == {"outcome": CANCELLED}


def test_options_that_are_not_a_list_cancel_rather_than_crash():
    assert DenyAll().permission(ask(options=None))["outcome"] == {
        "outcome": CANCELLED}


def test_an_option_without_an_id_is_not_selectable():
    policy = DenyAll()
    answer = policy.permission(ask(options=[{"kind": "reject_once"}]))
    assert answer["outcome"] == {"outcome": CANCELLED}


def test_denied_file_access_raises_rather_than_returning_empty_content():
    policy = DenyAll()
    with pytest.raises(PermissionError):
        policy.read_text_file({"sessionId": "s", "path": "/etc/hosts"})
    with pytest.raises(PermissionError):
        policy.write_text_file({"sessionId": "s", "path": "/x", "content": ""})


def test_every_refusal_lands_in_the_record_with_its_reason():
    policy = DenyAll()
    policy.permission(ask())
    with pytest.raises(PermissionError):
        policy.read_text_file({"path": "/etc/hosts"})
    assert [d.method for d in policy.decisions] == ["session/request_permission",
                                                    "fs/read_text_file"]
    assert all(d.allowed is False for d in policy.decisions)
    assert all(d.reason for d in policy.decisions)


def test_a_workspace_policy_reads_a_file_inside_its_root(tmp_path):
    (tmp_path / "note.txt").write_text("hello\n", encoding="utf-8")
    policy = WorkspacePolicy(tmp_path)
    answer = policy.read_text_file({"path": str(tmp_path / "note.txt")})
    assert answer == {"content": "hello\n"}
    assert policy.decisions[-1].allowed is True


def test_a_workspace_policy_refuses_a_path_outside_its_root(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    policy = WorkspacePolicy(tmp_path / "inner")
    (tmp_path / "inner").mkdir()
    with pytest.raises(OutsideRoot):
        policy.read_text_file({"path": str(outside)})
    assert policy.decisions[-1].allowed is False


def test_a_symlink_out_of_the_workspace_does_not_widen_it(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    try:
        (root / "link.txt").symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not let this process create symlinks")
    policy = WorkspacePolicy(root)
    with pytest.raises(OutsideRoot):
        policy.read_text_file({"path": str(root / "link.txt")})


def test_a_relative_path_is_refused_because_acp_paths_are_absolute(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    with pytest.raises(OutsideRoot):
        policy.read_text_file({"path": "note.txt"})
    with pytest.raises(OutsideRoot):
        policy.read_text_file({"path": ""})
    with pytest.raises(OutsideRoot):
        policy.read_text_file({})


def test_a_missing_file_inside_the_root_is_not_found_rather_than_forbidden(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    with pytest.raises(FileNotFoundError):
        policy.read_text_file({"path": str(tmp_path / "absent.txt")})
    assert policy.decisions[-1].reason == "no such file"


def test_a_line_and_limit_slice_the_file_one_based(tmp_path):
    (tmp_path / "f.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
    policy = WorkspacePolicy(tmp_path)
    path = str(tmp_path / "f.txt")
    assert policy.read_text_file({"path": path, "line": 2,
                                  "limit": 2}) == {"content": "b\nc\n"}
    assert policy.read_text_file({"path": path,
                                  "limit": 1}) == {"content": "a\n"}


def test_a_workspace_policy_is_read_only_until_writes_are_asked_for(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    assert policy.writes is False
    with pytest.raises(PermissionError):
        policy.write_text_file({"path": str(tmp_path / "new.txt"),
                                "content": "x"})
    assert not (tmp_path / "new.txt").exists()


def test_a_writing_workspace_policy_creates_parent_directories(tmp_path):
    policy = WorkspacePolicy(tmp_path, allow_writes=True)
    assert policy.writes is True
    target = tmp_path / "deep" / "nested" / "new.txt"
    assert policy.write_text_file({"path": str(target), "content": "x"}) == {}
    assert target.read_text(encoding="utf-8") == "x"


def test_a_write_outside_the_root_is_refused_before_anything_is_created(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    policy = WorkspacePolicy(root, allow_writes=True)
    escape = tmp_path / "escaped.txt"
    with pytest.raises(OutsideRoot):
        policy.write_text_file({"path": str(escape), "content": "x"})
    assert not escape.exists()


def test_a_write_without_string_content_is_refused(tmp_path):
    policy = WorkspacePolicy(tmp_path, allow_writes=True)
    with pytest.raises(ValueError):
        policy.write_text_file({"path": str(tmp_path / "f.txt"),
                                "content": {"not": "text"}})


def test_permission_stays_denied_under_a_workspace_policy_by_default(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    assert policy.permission(ask())["outcome"]["optionId"] == "no"
    policy = WorkspacePolicy(tmp_path, allow_permission=True)
    assert policy.permission(ask())["outcome"]["optionId"] == "yes"
    assert policy.decisions[-1].allowed is True


def test_allow_all_is_the_only_policy_that_says_yes_to_everything(tmp_path):
    policy = AllowAll()
    assert (policy.reads, policy.writes) == (True, True)
    target = tmp_path / "anywhere.txt"
    policy.write_text_file({"path": str(target), "content": "written"})
    assert policy.read_text_file({"path": str(target)}) == {
        "content": "written"}
    assert policy.permission(ask())["outcome"]["optionId"] == "yes"
    assert all(d.allowed for d in policy.decisions)

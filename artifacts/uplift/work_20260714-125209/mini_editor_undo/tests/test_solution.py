import pytest
from solution import edit


def test_type_and_cursor():
    assert edit(["type hello"]) == ("hello", 5)
    assert edit([]) == ("", 0)


def test_insert_middle_and_clamping():
    assert edit(["type bc", "left 99", "type a"]) == ("abc", 1)
    assert edit(["type ab", "left 1", "right 99"]) == ("ab", 2)


def test_type_payload_may_contain_spaces():
    assert edit(["type a b"]) == ("a b", 3)


def test_backspace_partial():
    assert edit(["type abc", "left 2", "backspace 5"]) == ("bc", 0)


def test_undo_restores_cursor_too():
    # cursor motion after the undone edit is discarded
    assert edit(["type ab", "type cd", "left 3", "undo"]) == ("ab", 2)


def test_undo_skips_noop_backspace():
    # a backspace that deleted nothing is never an undo target
    assert edit(["type ab", "left 2", "backspace 1", "undo"]) == ("", 0)


def test_undo_on_empty_stack_is_noop():
    assert edit(["undo", "undo"]) == ("", 0)


def test_undo_twice_pops_two_edits():
    assert edit(["type a", "type b", "undo", "undo"]) == ("", 0)


def test_malformed_commands_raise():
    for bad in (["delete 1"], ["type"], ["type "], ["left"], ["left 0"],
                ["left -2"], ["left 2x"], ["left 2 3"], ["undo 2"],
                ["backspace 0"], ["right +3"]):
        with pytest.raises(ValueError):
            edit(bad)


def test_no_mutation():
    cmds = ["type ab", "left 1", "undo"]
    snapshot = list(cmds)
    edit(cmds)
    assert cmds == snapshot

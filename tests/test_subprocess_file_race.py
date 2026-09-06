"""The race the `text_once_written` fixture exists to close.

A test that starts a real process and reads what it wrote has to decide when
the write has landed. `Path.exists()` is the obvious answer and the wrong one:
`open(path, "w")` publishes the name first and the bytes after, so a poll on
existence can return between the two and read an empty string. It cost one
windows-latest shard on a commit whose sibling run passed the same shard, and
it reached two different-looking failures from one cause -- an equality
assertion against `''` in `test_dap_policy.py`, and `int('')` in
`test_exec_oracle.py`.

Those two files skip or pass depending on the platform and the timing, which is
exactly why the fixture is checked here instead: the race is reconstructed on
purpose, so the guarantee is asserted rather than waited for.
"""
import threading
import time


def _publish_then_write(path, text, gap=0.3):
    """Create the file, wait, then put content in it: the subprocess race in
    the small. The handle is opened and left open across the gap because that
    is what `open(p, "w").write(...)` does inside a candidate script."""
    def run():
        handle = open(path, "w", encoding="utf-8")
        try:
            time.sleep(gap)
            handle.write(text)
        finally:
            handle.close()
    t = threading.Thread(target=run)
    t.start()
    return t


def test_a_file_that_exists_but_is_empty_is_not_read_as_its_content(
        tmp_path, text_once_written):
    # The load-bearing one. An `exists()` poll returns during the gap and reads
    # ''; this must return the payload instead, which means it waited.
    written = tmp_path / "late.txt"
    thread = _publish_then_write(written, "['kept', None, 'added']")
    try:
        assert written.exists() or True  # the name may already be there
        assert text_once_written(written, timeout=10.0) == "['kept', None, 'added']"
    finally:
        thread.join()


def test_a_file_that_never_gets_content_fails_and_says_which_half_was_missing(
        tmp_path, text_once_written):
    # A subprocess that created its output and died before writing is a
    # different fault from one that never started, and the message has to
    # separate them or the next reader debugs the wrong process.
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    try:
        text_once_written(empty, timeout=0.1, why="the candidate died early")
        raise AssertionError("an empty file was accepted as content")
    except AssertionError as exc:
        message = str(exc)
    assert "stayed empty" in message
    assert "the candidate died early" in message

    missing = tmp_path / "absent.txt"
    try:
        text_once_written(missing, timeout=0.1)
        raise AssertionError("a missing file was accepted as content")
    except AssertionError as exc:
        assert "never appeared" in str(exc)


def test_a_barrier_caller_gets_what_is_there_instead_of_an_exception(
        tmp_path, text_once_written):
    # `required=False` is for the call that only needs the write to have landed
    # before it does something else. Raising there would surface as a failure
    # inside a monkeypatched method rather than at the assertion that knows
    # what the missing file means.
    missing = tmp_path / "absent.txt"
    assert text_once_written(missing, timeout=0.05, required=False) == ""


def test_content_that_is_already_there_is_returned_without_waiting(
        tmp_path, text_once_written):
    # The common case must not pay the poll interval, or every call site that
    # reads an already-finished file gets slower for a race it never had.
    ready = tmp_path / "ready.txt"
    ready.write_text("done", encoding="utf-8")
    started = time.monotonic()
    assert text_once_written(ready, timeout=5.0) == "done"
    assert time.monotonic() - started < 0.5

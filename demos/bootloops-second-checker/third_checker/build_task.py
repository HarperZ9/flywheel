"""Rebuild the exact model prompt from task.txt and the public tool page text.

The page text is not redistributed in this repository. Save the text of
https://www.bootloops.ai/tools/receipt.html to a file and run:

    python third_checker/build_task.py PAGE.txt > task_full.txt

The script prints a warning on stderr when the page text or the rebuilt prompt
does not match the hashes recorded for the run; the page may have changed since.
"""
import hashlib
import pathlib
import sys

PAGE_SHA256 = "3edffafb1fac64fa8cac4b3fd01730cc368371f2b5d37c25705a8fc346d35481"
PROMPT_SHA256 = "b9949c109bbb283565c3e08f30bd1dc5b2bfd7c51080bc6a0f0c601a10da55ff"
HEAD_LINES = 130  # task.txt up to and including the tool page header line


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    here = pathlib.Path(__file__).resolve().parent
    head_lines = (here / "task.txt").read_bytes().splitlines(keepends=True)[:HEAD_LINES]
    page = pathlib.Path(argv[1]).read_bytes()
    prompt = b"".join(head_lines) + page
    for label, data, want in (("page text", page, PAGE_SHA256), ("prompt", prompt, PROMPT_SHA256)):
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            print(f"warning: {label} sha256 {got} differs from the run's {want}", file=sys.stderr)
    sys.stdout.buffer.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

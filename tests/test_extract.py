"""code-extraction falsifier — a fenced/prose model answer becomes runnable code."""
from harness.extract import extract_code

CODE = "def add(a, b):\n    return a + b"


def test_fenced_python_block():
    assert extract_code(f"```python\n{CODE}\n```").strip() == CODE


def test_fenced_no_language():
    assert extract_code(f"```\n{CODE}\n```").strip() == CODE


def test_prose_around_fence_is_dropped():
    txt = f"Sure! Here is the function:\n```python\n{CODE}\n```\nLet me know if you need more."
    assert extract_code(txt).strip() == CODE


def test_bare_code_passes_through():
    assert extract_code(CODE).strip() == CODE           # idempotent on clean code


def test_truncated_open_fence():
    # model hit max_new_tokens mid-answer: opening fence, no close
    assert extract_code(f"```python\n{CODE}").strip() == CODE


def test_multiple_blocks_join_in_order():
    txt = "```python\nimport math\n```\nand\n```python\n" + CODE + "\n```"
    out = extract_code(txt)
    assert "import math" in out and "def add" in out
    assert out.index("import math") < out.index("def add")


def test_empty_is_empty():
    assert extract_code("") == "" and extract_code("   ") == ""

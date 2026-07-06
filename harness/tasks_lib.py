"""tasks_lib.py — the held-out oracle task set (M7 benchmark fuel).

A curated, self-validating registry of code tasks with hidden pytest tests.
Materializes into the task-dir format harness/task.py expects. The curator
runs each reference solution against its own hidden tests — a task whose
reference solution FAILS its tests is a broken benchmark and is rejected.

Varied difficulty (easy/medium/hard) + edge cases (empty input, negatives,
duplicates) so M7 can measure pass rate across a real distribution, not one
task. This is the durable benchmark asset the whole program measures against.
"""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskSpec:
    task_id: str
    prompt: str
    candidate_filename: str
    solution: str
    hidden_tests: str
    difficulty: str = "medium"
    oracle_cmd: str = "python -m pytest tests/ -q"
    max_new_tokens: int = 256

    def task_json(self) -> dict:
        return {
            "task_id": self.task_id, "prompt": self.prompt,
            "oracle": "pytest", "oracle_cmd": self.oracle_cmd,
            "candidate_path": self.candidate_filename,
            "max_new_tokens": self.max_new_tokens,
        }


REGISTRY: list[TaskSpec] = [
    TaskSpec(
        "add_two", "Implement add(a, b) returning the sum of two integers.",
        "solution.py",
        "def add(a, b):\n    return a + b\n",
        "from solution import add\n"
        "def test_pos():\n    assert add(2,3)==5\n"
        "def test_neg():\n    assert add(-1,-1)==-2\n"
        "def test_zero():\n    assert add(0,5)==5\n",
        "easy"),
    TaskSpec(
        "max_of_three", "Implement max_of_three(a, b, c) returning the largest of three integers.",
        "solution.py",
        "def max_of_three(a, b, c):\n    return max(a, b, c)\n",
        "from solution import max_of_three\n"
        "def test_basic():\n    assert max_of_three(1,2,3)==3\n"
        "def test_neg():\n    assert max_of_three(-5,-1,-3)==-1\n"
        "def test_tie():\n    assert max_of_three(4,4,2)==4\n",
        "easy"),
    TaskSpec(
        "is_palindrome", "Implement is_palindrome(s) returning True if s is a palindrome, ignoring case and non-alphanumeric chars.",
        "solution.py",
        "def is_palindrome(s):\n    s = ''.join(c.lower() for c in s if c.isalnum())\n    return s == s[::-1]\n",
        "from solution import is_palindrome\n"
        "def test_simple():\n    assert is_palindrome('racecar')\n"
        "def test_case():\n    assert is_palindrome('RaceCar')\n"
        "def test_punct():\n    assert is_palindrome('A man, a plan, a canal: Panama')\n"
        "def test_no():\n    assert not is_palindrome('hello')\n"
        "def test_empty():\n    assert is_palindrome('')\n",
        "medium"),
    TaskSpec(
        "count_vowels", "Implement count_vowels(s) returning the number of vowels (a,e,i,o,u) in s, case-insensitive.",
        "solution.py",
        "def count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n",
        "from solution import count_vowels\n"
        "def test_lower():\n    assert count_vowels('hello')==2\n"
        "def test_upper():\n    assert count_vowels('HELLO')==2\n"
        "def test_none():\n    assert count_vowels('sky')==0\n"
        "def test_empty():\n    assert count_vowels('')==0\n",
        "medium"),
    TaskSpec(
        "dedupe_order", "Implement dedupe(items) removing duplicates from a list while preserving first-occurrence order.",
        "solution.py",
        "def dedupe(items):\n    seen = set(); out = []\n    for x in items:\n        if x not in seen:\n            seen.add(x); out.append(x)\n    return out\n",
        "from solution import dedupe\n"
        "def test_basic():\n    assert dedupe([1,2,2,3,1])==[1,2,3]\n"
        "def test_empty():\n    assert dedupe([])==[]\n"
        "def test_all_same():\n    assert dedupe([5,5,5])==[5]\n"
        "def test_strings():\n    assert dedupe(['a','b','a'])==['a','b']\n",
        "medium"),
    TaskSpec(
        "second_largest", "Implement second_largest(nums) returning the second-largest unique value. Return None for lists with fewer than 2 unique values.",
        "solution.py",
        "def second_largest(nums):\n    uniq = sorted(set(nums), reverse=True)\n    return uniq[1] if len(uniq) >= 2 else None\n",
        "from solution import second_largest\n"
        "def test_basic():\n    assert second_largest([3,1,4,1,5,9,2,6])==6\n"
        "def test_neg():\n    assert second_largest([-1,-5,-2])==-2\n"
        "def test_dups():\n    assert second_largest([5,5,5,3])==3\n"
        "def test_one():\n    assert second_largest([7]) is None\n"
        "def test_empty():\n    assert second_largest([]) is None\n",
        "hard"),
    TaskSpec(
        "fizzbuzz", "Implement fizzbuzz(n) returning a list of strings for 1..n: 'Fizz' for multiples of 3, 'Buzz' for 5, 'FizzBuzz' for both, else the number as a string.",
        "solution.py",
        "def fizzbuzz(n):\n    out = []\n    for i in range(1, n+1):\n        if i % 15 == 0:\n            out.append('FizzBuzz')\n        elif i % 3 == 0:\n            out.append('Fizz')\n        elif i % 5 == 0:\n            out.append('Buzz')\n        else:\n            out.append(str(i))\n    return out\n",
        "from solution import fizzbuzz\n"
        "def test_basic():\n    assert fizzbuzz(5)==['1','2','Fizz','4','Buzz']\n"
        "def test_fifteen():\n    r = fizzbuzz(15)\n    assert r[14]=='FizzBuzz' and r[2]=='Fizz' and r[4]=='Buzz'\n"
        "def test_empty():\n    assert fizzbuzz(0)==[]\n",
        "medium"),
    TaskSpec(
        "flatten_one", "Implement flatten_one(items) flattening a list by exactly one level: each element that is a list is spliced in; non-lists stay.",
        "solution.py",
        "def flatten_one(items):\n    out = []\n    for x in items:\n        if isinstance(x, list):\n            out.extend(x)\n        else:\n            out.append(x)\n    return out\n",
        "from solution import flatten_one\n"
        "def test_basic():\n    assert flatten_one([1,[2,3],4])==[1,2,3,4]\n"
        "def test_nested_stays():\n    assert flatten_one([[1,[2]]])==[1,[2]]\n"
        "def test_empty():\n    assert flatten_one([])==[]\n"
        "def test_no_lists():\n    assert flatten_one([1,2,3])==[1,2,3]\n",
        "medium"),
]


def materialize(spec: TaskSpec, dest_dir: str | Path) -> Path:
    dest = Path(dest_dir)
    skel = dest / "skeleton"
    skel.mkdir(parents=True, exist_ok=True)
    (skel / spec.candidate_filename).write_text("pass\n", encoding="utf-8")
    (skel / "tests").mkdir(exist_ok=True)
    (skel / "tests" / f"test_{spec.task_id}.py").write_text(
        spec.hidden_tests, encoding="utf-8")
    (dest / "task.json").write_text(
        json.dumps(spec.task_json(), indent=2), encoding="utf-8")
    return dest


def materialize_all(registry: list[TaskSpec], base_dir: str | Path) -> list[Path]:
    base = Path(base_dir)
    return [materialize(s, base / s.task_id) for s in registry]


def validate_spec(spec: TaskSpec, work_root: str | Path) -> bool:
    """Self-check: the reference solution must pass its own hidden tests. A
    benchmark task whose reference solution fails is broken — rejected."""
    from .task import load_task
    from .oracle import clear_bytecode, run_env
    work = Path(work_root) / spec.task_id
    materialize(spec, work)
    task = load_task(work, workdir=work / "validate_wd")
    task.candidate_full().write_text(spec.solution, encoding="utf-8")
    clear_bytecode(Path(task.workdir))
    r = subprocess.run(spec.oracle_cmd, cwd=task.workdir, shell=True,
                       capture_output=True, env=run_env(), timeout=30)
    return r.returncode == 0


def validate_registry(registry: list[TaskSpec], work_root: str | Path) -> dict:
    return {s.task_id: validate_spec(s, work_root) for s in registry}

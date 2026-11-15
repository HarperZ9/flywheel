from coherence_membrane.distill import readability_cost


def test_readability_cost_penalizes_code_golf_over_clear():
    clear = "def f(x):\n    y = x + 1\n    return y\n"
    golf = "def f(x):\n return (lambda y:y)(x+1) if x else (x+1)+0+0+0+0+0+0+0+0+0+0+0+0\n"
    # the golfed line is shorter in lines but crammed; clear must score lower (better)
    assert readability_cost(clear) < readability_cost(golf)


def test_readability_cost_is_deterministic():
    t = "a = 1\n    b = 2\n"
    assert readability_cost(t) == readability_cost(t)


def test_readability_cost_empty_is_zero_floor():
    assert readability_cost("") == 0.0


# Task 2: density and readability graders
from coherence_membrane.distill import density_grader, readability_grader, readability_cost
from coherence_membrane.refine import grade


def test_density_grader_rewards_smaller_rejects_bigger():
    orig = "x = 1\n" * 10                       # 60 bytes
    dg = density_grader(len(orig.encode("utf-8")))
    smaller = grade(dg, "x = 1\n" * 5)          # 30 bytes -> ratio 0.5 -> margin 0.5
    bigger = grade(dg, "x = 1\n" * 20)          # ratio 2.0 -> margin -1.0
    assert smaller.ok and smaller.margin > 0
    assert not bigger.ok


def test_readability_grader_rejects_worse_readability():
    orig = "a = 1\nb = 2\n"
    rg = readability_grader(readability_cost(orig))
    worse = grade(rg, "a=1;b=2;" + "z"*200 + "\n")   # one crammed line -> cost up -> margin < 0
    assert not worse.ok


# Task 3: behavior guard (tests runner, fail-closed)
from coherence_membrane.distill import command_guard


def test_command_guard_passes_on_exit_zero():
    assert command_guard("exit 0")(None) is True


def test_command_guard_fails_closed_on_nonzero_and_error():
    assert command_guard("exit 1")(None) is False
    assert command_guard("this_command_does_not_exist_xyz")(None) is False


def test_command_guard_none_is_unchecked_true():
    assert command_guard(None)(None) is True


# Task 4: distill_code wiring + witness record
import hashlib
from coherence_membrane.distill import distill_code, readability_cost


def test_distill_accepts_a_clean_smaller_candidate():
    original = "def f(x):\n    temp = x + 1\n    result = temp\n    return result\n"
    candidate = "def f(x):\n    return x + 1\n"               # smaller AND simpler
    rec = distill_code(original, candidate=candidate, behavior_guard=None)
    assert rec["verdict"] == "ACCEPTED"
    assert rec["gain"] > 1.0
    assert rec["candidate_sha256"] == hashlib.sha256(candidate.encode("utf-8")).hexdigest()


def test_distill_rejects_code_golf_even_if_smaller():
    original = "def f(x):\n    return x + 1\n"
    golf = "def f(x):return(x+1)"+ "#" + "z"*300 + "\n"        # LARGER than original (density also rejects)
    rec = distill_code(original, candidate=golf, behavior_guard=None)
    assert rec["verdict"] == "REJECTED"
    assert rec["short_axis"] == "readability"


def test_distill_rejects_smaller_but_crammed_candidate():
    """A candidate that is FEWER bytes but crammed onto one long line.
    Density must pass (fewer bytes) and readability must reject (line too long).
    This isolates the readability axis independently of density."""
    original = (
        "def scale(values, factor):\n"
        "    out = []\n"
        "    for v in values:\n"
        "        out.append(v * factor)\n"
        "    return out\n"
    )
    candidate = "def scale(values,factor):out=[];[out.append(v*factor) for v in values];return out\n"
    # Verify the fixture: candidate is genuinely smaller
    assert len(candidate.encode("utf-8")) < len(original.encode("utf-8")), (
        "fixture broken: candidate must have fewer bytes than original"
    )
    # Verify density passes independently
    from coherence_membrane.distill import density_grader
    from coherence_membrane.refine import grade
    assert grade(density_grader(len(original.encode("utf-8"))), candidate).ok is True, (
        "fixture broken: density grader must accept the candidate"
    )
    rec = distill_code(original, candidate=candidate, behavior_guard=None)
    assert rec["verdict"] == "REJECTED"
    assert rec["short_axis"] == "readability"


def test_distill_rejects_when_behavior_guard_fails():
    original = "x = 1\n" * 5
    rec = distill_code(original, candidate="x = 1\n", behavior_guard=lambda c: False)
    assert rec["verdict"] == "REJECTED"
    assert rec["short_axis"] in ("behavior", "density", "readability")  # guard short-circuits correctness


# Task 5: CLI distill --code
import json
from coherence_membrane.distill_cli import main


def test_cli_accepts_and_exits_zero(tmp_path, capsys):
    (tmp_path / "a.py").write_text("def f(x):\n    t = x + 1\n    return t\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    rc = main(["--code", "--original", str(tmp_path / "a.py"),
               "--candidate", str(tmp_path / "b.py"), "--json"])
    assert rc == 0
    rec = json.loads(capsys.readouterr().out)
    assert rec["verdict"] == "ACCEPTED" and rec["gain"] > 1.0


def test_cli_rejected_exits_one(tmp_path, capsys):
    (tmp_path / "a.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f(x):return(x+1)#" + "z"*300 + "\n", encoding="utf-8")
    rc = main(["--code", "--original", str(tmp_path / "a.py"), "--candidate", str(tmp_path / "b.py")])
    assert rc == 1


# Task 6: compressed and behavior_checked fields
def test_new_record_fields_compressed_and_behavior_checked():
    # An accepted clean-smaller candidate must have compressed=True
    original = "def f(x):\n    temp = x + 1\n    result = temp\n    return result\n"
    smaller = "def f(x):\n    return x + 1\n"
    rec = distill_code(original, candidate=smaller, behavior_guard=None)
    assert rec["verdict"] == "ACCEPTED"
    assert rec["compressed"] is True

    # behavior_checked is False when no guard is supplied
    rec_no_guard = distill_code(original, candidate=smaller, behavior_guard=None)
    assert rec_no_guard["behavior_checked"] is False

    # behavior_checked is True when a guard is supplied
    rec_with_guard = distill_code(original, candidate=smaller, behavior_guard=lambda c: True)
    assert rec_with_guard["behavior_checked"] is True

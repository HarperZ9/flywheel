"""I10 and A13: every pattern runs in time linear in its input.

Each rule is fed about 1 MiB of near-miss input shaped to be its worst case:
long runs of its own character class, repeated prefixes, openers without
closers. Its budget is a ratio to a baseline measured beside it in the same
process: one linear pattern that never matches, run over a text of the same
length. The two run in alternation five times with the collector off, and
the best time of each goes into the ratio, so load on the machine slows both
alike and the runs it hit hardest drop out. The rule may take at most RATIO
times the baseline. The slowest honest rule, credential_assignment with 23
patterns, measured 3.2 to 3.4 times the baseline on Windows under Python 3.12
and 3.13 and on Linux under 3.12, and 4.3 times on Linux under 3.13.
Catastrophic backtracking measures hundreds of times the baseline on 16 KiB
and grows with the input; the control below holds the check to that.

This replaced a budget of 50 ms per MiB, scaled by a calibration scan timed
once per process, which allowed 3.6 times the calibration. It failed that rule
on a hosted Linux runner at 84.6 ms against 82.8: the margin was thin on every
interpreter, and load that came between the calibration and the rule counted
against the rule. Under bursty load from 48 busy processes on 24 cores the
old check failed five runs of six and this one none.

Floods are measured apart: input made of real matches, or of candidates a
validator must reject (IBAN-shaped strings that fail mod 97). Their cost is
one Python-level check per candidate, so it is linear but not bounded by the
pattern budget; the flood test asserts that 2 MiB costs at most 20 times a
quarter MiB (linear is 8, quadratic 64) in one of up to three rounds. A scan that runs past its per-call budget stops with
SCAN_BUDGET_EXCEEDED; that check sits between windows and rules, so it cannot
interrupt one catastrophic pattern, which is why every pattern is written
linear and tested here.
"""
import gc
import math
import re
import time

import pytest

from harness import trace_redact, trace_redact_rules as rules

MIB = 1 << 20


def _fill(unit: str, size: int = MIB) -> str:
    return (unit * (size // len(unit) + 1))[:size]


ADVERSARIAL = {
    "pem_private_key": ["-----BEGIN ", "-----BEGIN RSA PRIVATE KEY-----\n-----END "],
    "aws_access_key_id": ["AKIA" + "A" * 15 + " ", "A"],
    "aws_secret_assignment": ["aws_secret_access_key=" + "A" * 39 + " "],
    "github_token": ["ghp_" + "a" * 29 + " ", "github_pat_" + "a" * 21 + " "],
    "sk_api_key": ["sk-" + "a" * 19 + " ", "sk-"],
    "slack_token": ["xoxb-" + "a" * 9 + " "],
    "stripe_key": ["sk_live_" + "a" * 9 + " "],
    "google_api_key": ["AIza" + "a" * 34 + " "],
    "jwt": ["eyJaaaaaaaaaa.", "eyJaaaaaaaaaa.eyJbbbbbbbbbb."],
    "bearer_token": ["bearer ", "bearer " + "a" * 15 + " "],
    "basic_auth": ["basic ", "basic QUFB "],
    "url_userinfo": ["https://" + "a" * 255 + " ", "://"],
    "credential_assignment": ["password", "a", "password=" + "a" * 7 + " ", "tokentoken"],
    "azure_key_assignment": ["AccountKey=" + "A" * 19 + " "],
    "npm_token": ["npm_" + "a" * 35 + " "],
    "pypi_token": ["pypi-AgEIcHlwaS5vcmc" + "a" * 49 + " "],
    "hf_token": ["hf_" + "a" * 29 + " "],
    "cookie_header": ["cookie:", "\nCookie: " + "a" * 20],
    "url_signature_param": ["?sig", "&sig="],
    "oauth_code_param": ["?code=" + "c" * 10 + " ", "https://a/?code="],
    "docker_auth": ['"auth":"' + "A" * 7 + '"'],
    "kubeconfig_secret": ["client-key-data: " + "a" * 15 + "\n", "token:"],
    "age_secret_key": ["AGE-SECRET-KEY-1" + "A" * 57 + " "],
    "putty_key": ["PuTTY-User-Key-File-"],
    "email": ["a", "a@", "@a.", "a@b."],
    "phone": ["1", "(415) ", "+1"],
    "card_number": ["1", "4 ", "4-"],
    "us_ssn": ["123-45-", "1"],
    "iban": ["GB82", "GB82 ABC ", "GB82 ABCD"],
    "ipv4": ["1.", "255.255.255."],
    "ipv6": [":", "a:", "::", "abcd:"],
    "lat_long": ["1.", "47.60, ", "47.6062 "],
}


def test_every_rule_has_adversarial_inputs():
    assert set(ADVERSARIAL) == {r.id for r in rules.RULES}


# The baseline does work at every position of "4 4 4 ..." and never matches.
_BASELINE = re.compile(r"(?<![\d])\d{4}(?![\d])")
RATIO = 8
REPEATS = 5


def _ratio_to_baseline(rule, text: str) -> float:
    """The rule's best time over the baseline's best time, the two timed in
    alternation over texts of one length with the collector off, so a
    collection of a heap earlier tests left behind lands in neither. A scan
    that runs past its own per-call budget stops with SCAN_BUDGET_EXCEEDED,
    and that counts as infinitely slow."""
    base_text = _fill("4 ", len(text))
    best_rule = best_base = math.inf
    collecting = gc.isenabled()
    gc.disable()
    try:
        for _ in range(REPEATS):
            start = time.perf_counter()
            list(_BASELINE.finditer(base_text))
            best_base = min(best_base, time.perf_counter() - start)
            start = time.perf_counter()
            try:
                list(trace_redact.scan(text, rules_=(rule,)))
            except trace_redact.ScanBudgetExceeded:
                return math.inf
            best_rule = min(best_rule, time.perf_counter() - start)
    finally:
        if collecting:
            gc.enable()
    return best_rule / best_base


@pytest.mark.timeout(120)
@pytest.mark.parametrize("rule", rules.RULES, ids=lambda r: r.id)
def test_each_rule_meets_its_budget_on_adversarial_input(rule):
    for unit in ADVERSARIAL[rule.id]:
        ratio = _ratio_to_baseline(rule, _fill(unit))
        assert ratio <= RATIO, f"{rule.id} took {ratio:.1f} times the baseline on {unit!r}"


def _pattern_rule(rule_id: str, pattern: str):
    return rules.Rule(rule_id, "credential", "secret", re.compile(pattern), note="test only")


@pytest.mark.timeout(120)
@pytest.mark.parametrize("size", [16 * 1024, MIB], ids=["16KiB", "1MiB"])
def test_the_budget_fails_a_pattern_that_backtracks(size):
    """False-success control. On a run of letters, `[a-z]+=` starts at every
    position, takes the rest of the run and gives it back one letter at a time
    looking for `=`, so its cost grows with the square of the run. On 16 KiB,
    inside one window, it measures hundreds of times the baseline, more than
    ten times the bound. On 1 MiB its first 64 KiB window takes seconds and the
    scan stops with SCAN_BUDGET_EXCEEDED, which counts as infinitely slow. The
    same pattern written as the catalog writes it, with a lookbehind and a
    possessive run, passes on the same text: the check separates the two by
    their backtracking alone."""
    text = _fill("a", size)
    backtracking = _pattern_rule("backtracking_injected", r"[a-z]+=")
    assert _ratio_to_baseline(backtracking, text) > 10 * RATIO
    linear = _pattern_rule("linear_injected", r"(?<![a-z])[a-z]++=")
    assert _ratio_to_baseline(linear, text) <= RATIO


FLOODS = {
    "iban": "GB82 ABCD ",
    "lat_long": "47.6062, ",
    "jwt": "eyJ" + "a" * 12 + ".eyJ" + "a" * 8 + "." + "a" * 16 + " ",
    "card_number": "4111 1111 1111 1112 ",
    "github_token": "ghp_" + "x" * 36 + " ",
    "email": "a@b.cd ",
    "credential_assignment": "password=aaaaaaaa ",
}


def _flood_pair(rule, unit):
    """Best of five for a quarter MiB and for 2 MiB, measured alternately so
    load on the machine hits both sizes alike. Linear cost gives a ratio near
    8; quadratic cost gives 64.

    The heap already in the process is frozen while the pair is timed. A full
    garbage collection walks every live object, and the 2 MiB scan allocates
    enough to set off collections the quarter MiB scan does not, so in a
    process that already ran thousands of tests the ratio measured that heap,
    not the rule: with 8 million live objects github_token measured 26.6,
    and 8.7 with them frozen."""
    texts = [(unit * (size // len(unit) + 1))[:size] for size in (MIB // 4, 2 * MIB)]
    best = [float("inf"), float("inf")]
    gc.collect()
    gc.freeze()
    try:
        for _ in range(5):
            for index, text in enumerate(texts):
                start = time.perf_counter()
                trace_redact.scan(text, rules_=(rule,))
                best[index] = min(best[index], time.perf_counter() - start)
    finally:
        gc.unfreeze()
    return best


def _linear(small, large) -> bool:
    """2.5 times the linear ratio of 8, and still 3 times under quadratic."""
    return large <= 20 * small + 0.010


ROUNDS = 3


def _linear_in_some_round(rule, unit) -> tuple[bool, list]:
    """Up to ROUNDS measurements of the pair; stops at the first one inside the
    bound. Memory traffic from other processes slows the 2 MiB scan more than
    the quarter MiB one, which fits in cache: 24 processes streaming 64 MiB
    each pushed one github_token round to 26.6 while the next five stayed
    between 14 and 19.6. A rule whose cost grows faster than linear misses
    every round, so a repeat cannot pass it (see the quadratic control below)."""
    rounds = []
    for _ in range(ROUNDS):
        small, large = _flood_pair(rule, unit)
        rounds.append((small, large))
        if _linear(small, large):
            return True, rounds
    return False, rounds


@pytest.mark.timeout(240)
@pytest.mark.parametrize("rule_id", sorted(FLOODS))
def test_match_and_candidate_floods_scale_linearly(rule_id):
    rule = next(r for r in rules.RULES if r.id == rule_id)
    ok, rounds = _linear_in_some_round(rule, FLOODS[rule_id])
    assert ok, (rule_id, rounds)


@pytest.mark.timeout(120)
def test_the_linearity_check_fails_a_quadratic_rule():
    """False-success control: a rule whose cost grows with the square of its
    input must fail the ratio the flood test applies."""
    def quadratic(text):
        time.sleep(0.2 * (len(text) / MIB) ** 2)
        return iter(())
    rule = rules.Rule("quadratic_injected", "credential", "secret", None, note="test only",
                      finder=quadratic)
    # Every round misses, so the repeat the flood test allows cannot rescue it.
    ok, rounds = _linear_in_some_round(rule, "x")
    assert not ok and len(rounds) == ROUNDS
    assert not any(_linear(small, large) for small, large in rounds)


def test_an_injected_slow_rule_stops_the_scan_with_the_budget_code():
    def slow_finder(text):
        time.sleep(0.05)
        return iter(())
    slow = rules.Rule("slow_injected", "credential", "secret", None, note="test only",
                      finder=slow_finder)
    with pytest.raises(trace_redact.ScanBudgetExceeded) as caught:
        list(trace_redact.scan("x" * (256 * 1024), rules_=(slow,), budget_s=0.01))
    assert caught.value.code == "SCAN_BUDGET_EXCEEDED"


def test_long_strings_are_scanned_in_overlapping_windows_without_losing_a_token():
    token = "gh" + "p_" + "x" * 36
    boundary = trace_redact.WINDOW - 10
    text = "a " * (boundary // 2) + token + " b" * 1000
    hits = list(trace_redact.scan(text))
    assert [(h.rule_id, text[h.start:h.end]) for h in hits] == [("github_token", token)]

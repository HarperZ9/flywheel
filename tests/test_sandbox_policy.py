"""The one hole a confined macOS run gets, and where it has to sit.

The rest of the profile is asserted in `test_posix_sandbox.py`, next to the
argv it ships with. What is here is the part a reader cannot check by
reading: Seatbelt takes the last matching rule, so an allow written above
the deny is a line that looks like a permission and grants nothing.
"""
import pytest

from harness.sandbox_policy import (ProfileRefused, posix_path, sbpl_profile,
                                    seatbelt_argv)


def lines(profile):
    return profile.strip().split("\n")


def test_a_profile_nobody_asked_for_a_port_has_no_outbound_rule():
    """The default is unchanged. A run that named no proxy gets the denial
    it got before this parameter existed."""
    profile = sbpl_profile("/w", "/s")
    assert "network-outbound" not in profile
    assert "(deny network*)" in profile


def test_the_allow_follows_the_deny_and_not_the_other_way_round():
    """The whole mechanism is this ordering.

    Seatbelt applies the last rule that matches, so these two lines in the
    other order are a profile that denies every connection while appearing
    to permit one.
    """
    written = lines(sbpl_profile("/w", "/s", egress_port=8931))
    assert written.index("(deny network*)") < written.index(
        '(allow network-outbound (remote tcp "localhost:8931"))')


def test_the_hole_names_one_port_on_the_loopback_interface():
    profile = sbpl_profile("/w", "/s", egress_port=8931)
    assert '(remote tcp "localhost:8931")' in profile
    assert "(allow network*)" not in profile, (
        "a blanket allow would make the port in the rule decoration")


def test_resolution_stays_denied_so_the_proxy_is_given_a_name():
    """Load-bearing rather than incidental.

    A confined process that could resolve would hand the proxy an address it
    picked, and the policy the proxy applies is written about names. Denying
    resolution is what makes the name in the CONNECT line the name the
    client meant.
    """
    profile = sbpl_profile("/w", "/s", egress_port=8931)
    assert "udp" not in profile
    assert profile.count("network-outbound") == 1


def test_an_open_network_gets_no_hole_because_it_needs_none():
    """A run that was granted the network has no deny to punch through, and
    a rule allowing one port inside an open policy would read like a limit
    that is not there."""
    profile = sbpl_profile("/w", "/s", network=True, egress_port=8931)
    assert "network-outbound" not in profile
    assert "(deny network*)" not in profile


@pytest.mark.parametrize("port", [0, -1, 65536, "8931", 8931.0, True])
def test_a_port_that_is_not_a_port_never_reaches_the_profile_text(port):
    """The profile is text the kernel parses. Anything else written into it
    is a line whose meaning depends on how `sandbox-exec` reads it.

    `None` is absent from this list on purpose. It is how a caller says
    there is no proxy, and the first test in this file is what holds it to
    meaning that.
    """
    with pytest.raises(ProfileRefused):
        sbpl_profile("/w", "/s", egress_port=port)


def test_both_backends_spell_a_path_the_same_way():
    """One speller, so the argv and the record cannot disagree.

    A Windows host building either of these describes a run on a POSIX one,
    so the separator is the target's and not the caller's.
    """
    assert posix_path("C:\\dev\\repo") == "C:/dev/repo"
    assert posix_path("/tmp/scratch") == "/tmp/scratch"
    assert '(subpath "C:/dev/repo")' in sbpl_profile("C:\\dev\\repo", "/s")


def test_the_argv_carries_the_profile_and_not_a_path_to_one():
    argv = seatbelt_argv("sandbox-exec", "(version 1)\n", "echo hi")
    assert argv[:2] == ["sandbox-exec", "-p"]
    assert argv[2].startswith("(version 1)")

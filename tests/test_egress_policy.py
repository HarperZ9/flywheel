"""The allowlist, and the two things it deliberately does not promise.

Everything here runs on any host. The policy opens no socket and resolves
no name, which is why it can be read in a diff and asserted from Windows.
"""
import pytest

from harness.egress_policy import (DEFAULT_PORTS, EgressPolicy, PolicyRefused,
                                   blocked_address)


def test_an_exact_host_matches_and_a_neighbour_does_not():
    policy = EgressPolicy(hosts=("pypi.org",))
    assert policy.allows("pypi.org", 443)
    assert not policy.allows("evil-pypi.org", 443)
    assert not policy.allows("pypi.org.attacker.test", 443)


def test_a_wildcard_covers_subdomains_and_not_the_bare_name():
    """The rule is written down because both readings are defensible.

    `*.` is a subdomain rule. An operator who wants the bare name too has to
    say so, which is one more line in a policy and no guessing in a matcher.
    """
    policy = EgressPolicy(hosts=("*.pypi.org",))
    assert policy.allows("files.pypi.org", 443)
    assert policy.allows("a.b.pypi.org", 443)
    assert not policy.allows("pypi.org", 443)
    assert not policy.allows("notpypi.org", 443)


def test_case_and_a_trailing_dot_are_the_same_host():
    policy = EgressPolicy(hosts=("PyPI.org.",))
    assert policy.hosts == ("pypi.org",)
    assert policy.allows("PYPI.ORG", 443)
    assert policy.allows("pypi.org.", 443)


def test_the_port_is_part_of_the_rule():
    policy = EgressPolicy(hosts=("pypi.org",), ports=(443,))
    assert not policy.allows("pypi.org", 80)
    assert EgressPolicy(hosts=("pypi.org",), ports=(80, 443)).allows(
        "pypi.org", 80)


def test_the_default_port_set_carries_no_cleartext_route():
    """A default including 80 would hand every policy a route nobody wrote."""
    assert DEFAULT_PORTS == (443,)


def test_an_empty_policy_denies_everything():
    """The right answer for a run that named nothing, and it has to be the
    answer a bare constructor gives."""
    assert not EgressPolicy().allows("pypi.org", 443)
    assert EgressPolicy().summary() == "[egress: no host allowed]"


@pytest.mark.parametrize("pattern", [
    "*", "**.pypi.org", "pypi.*.org", "py*pi.org", "", "   ", ".",
    "pypi.org:443", "https://pypi.org", "pypi.org/simple", "user@pypi.org",
    "pypi.org?x=1", "[::1]", "a b.org", 7, None,
])
def test_a_pattern_that_could_be_read_two_ways_is_refused(pattern):
    """Not a best effort. A guess here permits a host nobody wrote down."""
    with pytest.raises(PolicyRefused):
        EgressPolicy(hosts=(pattern,))


@pytest.mark.parametrize("port", [0, -1, 65536, "443", 443.0, True, None])
def test_a_port_that_is_not_a_port_is_refused(port):
    with pytest.raises(PolicyRefused):
        EgressPolicy(hosts=("pypi.org",), ports=(port,))


def test_a_client_may_not_ask_for_a_wildcard():
    """The pattern language belongs to the policy author.

    A request naming `*.pypi.org` is a client asking to be matched by the
    rule instead of against it, and the string comparison would agree.
    """
    policy = EgressPolicy(hosts=("*.pypi.org",))
    assert not policy.allows("*.pypi.org", 443)


def test_a_name_list_is_not_an_address_list():
    """Stated in the module docstring, enforced here.

    A client that connects by address presents no name to match, so an
    address is reachable only when the address itself was written down. The
    second half matters more: an address must not fall through a name
    wildcard because its text happens to end the right way.
    """
    named = EgressPolicy(hosts=("*.3.4",))
    assert not named.allows("1.2.3.4", 443)
    written = EgressPolicy(hosts=("1.2.3.4",))
    assert written.allows("1.2.3.4", 443)


@pytest.mark.parametrize("address,reason", [
    ("127.0.0.1", "loopback"),
    ("::1", "loopback"),
    ("169.254.169.254", "link-local"),
    ("10.0.0.5", "private"),
    ("192.168.1.1", "private"),
    ("172.16.0.1", "private"),
    ("0.0.0.0", "unspecified"),
    ("224.0.0.1", "multicast"),
    ("fe80::1", "link-local"),
    ("fd00::1", "private"),
])
def test_an_allowed_name_may_not_resolve_onto_the_host(address, reason):
    """The check after resolution, and the reason it exists.

    A name in the list can answer with the machine the sandbox is running on
    or with the metadata service of the instance it is running in. Both are
    named in the answer and neither is named in the list, so a policy that
    stopped at the name would carry the request to either.
    """
    assert blocked_address(address) == reason


@pytest.mark.parametrize("address", [
    "::ffff:127.0.0.1", "::ffff:169.254.169.254", "::ffff:10.0.0.1",
])
def test_an_ipv4_address_wrapped_in_ipv6_is_still_that_address(address):
    """`IPv6Address.is_loopback` answers False about `::ffff:127.0.0.1`.

    A guard that asked the property directly would pass the one address it
    exists to stop, and which Python version folds mapped addresses into
    `is_private` has changed under this code before.
    """
    assert blocked_address(address) is not None


def test_a_public_address_is_not_blocked():
    """A control. Every case above would also pass if this always refused."""
    assert blocked_address("93.184.216.34") is None
    assert blocked_address("2606:4700::1") is None


def test_junk_where_an_address_belongs_is_a_refusal_and_not_a_pass():
    assert blocked_address("pypi.org") == "not an address"
    assert blocked_address("") == "not an address"


def test_the_record_names_the_rules_and_the_summary_counts_them():
    policy = EgressPolicy(hosts=("pypi.org", "*.pythonhosted.org"),
                          ports=(443,))
    record = policy.record()
    assert record["hosts"] == ["pypi.org", "*.pythonhosted.org"]
    assert record["ports"] == [443]
    assert record["schema"].startswith("flywheel.egress-policy/")
    assert policy.summary() == "[egress: 2 host rules on port 443]"

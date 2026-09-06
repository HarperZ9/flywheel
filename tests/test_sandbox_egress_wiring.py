"""Where the route meets the two backends.

The route is built and tested in `test_egress_route`. What is asserted here
is that each backend receives the half it can use, that the record and the
argv agree about whether a route applies, and that a confined command is
told where the proxy is.
"""
from harness.egress_policy import EgressPolicy, PolicyRefused
from harness.egress_route import EgressRoute, RouteUnavailable
from harness.posix_sandbox import (build, describe, posix_run, routed,
                                   with_egress)
from harness.sandboxed_runner import _egress_line, _posix_sandboxed_run

ROUTE = EgressRoute("bwrap", "/scratch/egress.sock", 8931,
                    hosts=("pypi.org", "*.githubusercontent.com"),
                    ports=(443,))
MAC = EgressRoute("seatbelt", "127.0.0.1:8931", 8931, hosts=("pypi.org",),
                  ports=(443,))


def test_the_bridge_runs_inside_the_namespace_and_the_shell_is_its_child():
    """Ordering, because the bridge has to hold the port the shell dials.

    `--` ends bubblewrap's own arguments, so everything after it is the
    program bubblewrap execs inside the namespace. The shell has to follow
    the bridge there, not precede it.
    """
    argv = build("bwrap", "bwrap", "/w", "/s", "pip install x", egress=ROUTE)
    after = argv[argv.index("--") + 1:]
    assert after[1].endswith("egress_bridge.py")
    assert after.index("/bin/sh") > after.index("--socket")
    assert after[-3:] == ["/bin/sh", "-c", "pip install x"]


def test_a_run_with_no_route_has_the_argv_it_always_had():
    argv = build("bwrap", "bwrap", "/w", "/s", "ls")
    assert argv[argv.index("--") + 1:] == ["/bin/sh", "-c", "ls"]


def test_the_mac_backend_gets_a_port_and_the_linux_one_gets_a_bridge():
    """One route object, two halves. A caller cannot hand the wrong half to
    the wrong backend because it never holds the halves separately."""
    profile = build("seatbelt", "sandbox-exec", "/w", "/s", "ls",
                    egress=MAC)[2]
    assert 'network-outbound (remote tcp "localhost:8931")' in profile
    argv = build("bwrap", "bwrap", "/w", "/s", "ls", egress=ROUTE)
    assert "8931" in argv and "egress_bridge.py" in " ".join(argv)


def test_an_open_network_drops_the_route_from_the_argv_and_the_record():
    """Nothing filters a run that already has the network.

    A record naming host rules there would describe a limit no kernel is
    holding, and a bridge in the argv would be a process forwarding to a
    proxy the run has no reason to use.
    """
    assert routed(ROUTE, True) is None
    argv = build("bwrap", "bwrap", "/w", "/s", "ls", network=True,
                 egress=ROUTE)
    assert "egress_bridge.py" not in " ".join(argv)
    profile = build("seatbelt", "sb", "/w", "/s", "ls", network=True,
                    egress=MAC)[2]
    assert "network-outbound" not in profile
    written = describe("bwrap", "/w", "/s", network=True,
                       egress=ROUTE).record()
    assert written["egress_hosts"] == [] and written["egress_port"] is None


def test_the_record_carries_the_rules_the_proxy_was_holding():
    written = describe("bwrap", "/w", "/s", egress=ROUTE).record()
    assert written["egress_hosts"] == ["pypi.org", "*.githubusercontent.com"]
    assert written["egress_port"] == 8931
    assert written["network"] is False


def test_the_summary_has_a_third_state_because_the_network_has_three():
    """A proxied run is neither open nor denied. Calling it either would be
    wrong in a direction a reader of the line cannot recover from."""
    assert "network denied except 2 host rules" in describe(
        "bwrap", "/w", "/s", egress=ROUTE).summary()
    assert "network denied except 1 host rule]" in describe(
        "seatbelt", "/w", "/s", egress=MAC).summary()
    assert "network denied]" in describe("bwrap", "/w", "/s").summary()
    assert "network allowed" in describe("bwrap", "/w", "/s",
                                         network=True).summary()


def test_the_command_is_told_where_the_proxy_is():
    before = {"PATH": "/usr/bin"}
    after = with_egress(before, ROUTE)
    assert after["HTTPS_PROXY"] == "http://127.0.0.1:8931"
    assert after["PATH"] == "/usr/bin"
    assert before == {"PATH": "/usr/bin"}, (
        "the caller's environment is often reused by a later run, and a "
        "proxy address that outlived its listener points at nothing")


def test_a_run_with_no_route_gets_its_environment_back_unchanged():
    before = {"PATH": "/usr/bin"}
    assert with_egress(before, None) is before


def test_a_confined_run_reaches_the_runner_with_both_the_argv_and_the_env():
    """The whole path, with the host's programs injected.

    Everything above is a builder. This is the one assertion that the
    builders are wired to each other rather than merely correct apart.
    """
    seen = {}

    def runner(argv, root, env, timeout_seconds):
        seen["argv"], seen["env"] = argv, env
        return 0, ""

    rc, out, plan = posix_run(
        "pip install x", "/w", "/s", env={"PATH": "/usr/bin"},
        network=False, egress=ROUTE, platform="linux",
        which=lambda p: "/usr/bin/bwrap", probe=lambda b, p: True,
        runner=runner)
    assert rc == 0
    assert seen["env"]["HTTP_PROXY"] == "http://127.0.0.1:8931"
    assert "egress_bridge.py" in " ".join(seen["argv"])
    assert plan.record()["egress_hosts"] == ["pypi.org",
                                             "*.githubusercontent.com"]


def asked(host, allowed, reason=""):
    return {"host": host, "port": 443, "allowed": allowed, "reason": reason}


def test_a_run_that_asked_the_network_for_nothing_gets_no_egress_line():
    # An empty line joined into the header would put a blank line between
    # the confinement summary and the command's own first line of output.
    assert _egress_line([]) == ""


def test_the_allowed_requests_are_counted_because_the_output_already_has_them():
    line = _egress_line([asked("pypi.org", True), asked("pypi.org", True)])
    assert line == "[egress: 2 allowed]"


def test_a_refusal_is_named_because_the_command_will_describe_it_wrong():
    """What the run could not reach, in the run's own transcript.

    A command that was refused sees a connection it could not make and
    reports something about its retry logic. The host it wanted is the one
    fact the operator needs and the one the command does not print.
    """
    line = _egress_line([asked("pypi.org", True),
                         asked("evil.example", False, "not in policy"),
                         asked("169.254.169.254", False, "link-local")])
    assert line.startswith("[egress: 1 allowed, 2 refused: ")
    assert "evil.example not in policy" in line
    assert "169.254.169.254 link-local" in line


def test_one_host_refused_twenty_times_is_named_once():
    # A retrying client asks for the same host until it gives up, and a line
    # that repeated the host per attempt would bury the other refusals.
    line = _egress_line([asked("evil.example", False, "not in policy")] * 20)
    assert line == "[egress: 0 allowed, 20 refused: evil.example not in policy]"


def test_a_policy_that_cannot_be_read_stops_the_run(monkeypatch):
    """The one moment the feature was wanted is not the moment to default.

    An operator typed a policy and got it wrong. Running the command on the
    open network there would carry out the request they meant to restrict,
    under a variable name that says it was restricted.
    """
    def refuse(environ=None):
        raise PolicyRefused("port is outside 1-65535: 99999")

    monkeypatch.setattr("harness.egress_policy.from_env", refuse)
    ok, out = _posix_sandboxed_run("curl x", ".", None, 5)
    assert ok is False
    assert out.startswith("[denied] egress policy is unreadable")
    assert "99999" in out


def test_a_policy_with_no_route_stops_the_run_rather_than_opening_it(
        monkeypatch):
    def no_route(policy, backend, scratch, **kw):
        raise RouteUnavailable("no route for backend: chroot")

    monkeypatch.setattr("harness.egress_policy.from_env",
                        lambda environ=None: EgressPolicy(hosts=("pypi.org",)))
    monkeypatch.setattr("harness.posix_sandbox.backend_for", lambda: "bwrap")
    monkeypatch.setattr("harness.egress_route.open_route", no_route)
    ran = []
    monkeypatch.setattr("harness.posix_sandbox.posix_run",
                        lambda *a, **k: ran.append(a) or (0, "", None))
    ok, out = _posix_sandboxed_run("curl x", ".", None, 5)
    assert (ok, ran) == (False, [])
    assert out.startswith("[denied] no egress route for this run")


def test_no_policy_leaves_the_network_where_the_parity_argument_put_it(
        monkeypatch):
    """The default is unchanged, and this is what says so.

    Denying the network by default would make one command succeed on Linux
    and fail on Windows for a reason no caller asked about. The variable is
    the whole on-switch.
    """
    seen = {}

    def run(cmd, root, work, **kw):
        seen.update(kw)
        return 0, "hi", describe("bwrap", root, work, network=kw["network"])

    monkeypatch.setattr("harness.egress_policy.from_env",
                        lambda environ=None: None)
    monkeypatch.setattr("harness.posix_sandbox.posix_run", run)
    ok, out = _posix_sandboxed_run("ls", ".", None, 5)
    assert (ok, seen["network"], seen["egress"]) == (True, True, None)
    assert "network allowed" in out
    assert "[egress:" not in out, (
        "a run nobody filtered has no egress line to print")


class FakeRoute:
    """An opened route that records whether it was closed."""

    def __init__(self, attempts):
        self.route, self.closed = ROUTE, False
        self._attempts = attempts

    def record(self):
        return {"attempts": self._attempts}

    def close(self):
        self.closed = True


def test_a_policy_denies_the_network_around_the_proxy_and_reports_both(
        monkeypatch):
    """The network has to be off for the proxy to be the only way out.

    An open network beside a proxy is a proxy nothing has to use, and
    `routed` would then drop the route from the record while the run kept
    the whole internet.
    """
    seen, opened = {}, FakeRoute([asked("pypi.org", True),
                                  asked("evil.example", False, "not in policy")])

    def run(cmd, root, work, **kw):
        seen.update(kw)
        return 0, "done", describe("bwrap", root, work, network=kw["network"],
                                   egress=kw["egress"])

    monkeypatch.setattr("harness.egress_policy.from_env",
                        lambda environ=None: EgressPolicy(hosts=("pypi.org",)))
    monkeypatch.setattr("harness.posix_sandbox.backend_for", lambda: "bwrap")
    monkeypatch.setattr("harness.egress_route.open_route",
                        lambda *a, **k: opened)
    monkeypatch.setattr("harness.posix_sandbox.posix_run", run)
    ok, out = _posix_sandboxed_run("pip install x", ".", None, 5)
    assert (ok, seen["network"], seen["egress"]) == (True, False, ROUTE)
    assert "network denied except 2 host rules" in out
    assert "[egress: 1 allowed, 1 refused: evil.example not in policy]" in out
    assert opened.closed, (
        "the listener outlives the run unless the route is closed, and the "
        "next run on this host would find the port taken")

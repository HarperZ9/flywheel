"""Falsifiers for the lane registry's own declarations.

test_lanes.py is about how the roster behaves: what it reports for a lane that
is installed, declared or missing. This file is about whether the declarations
themselves are still true, which is a separate failure mode. A registry can be
internally consistent, pass every roster test, and still name a version nobody
publishes or keep a disabled reason for a package that shipped months ago.

Both checks here exist because that happened. On 2026-09-22 five lanes declared
versions the index had moved past, and two carried a disabled reason for
distributions that were live.
"""
import re

from harness.lanes_registry import LANES

# Lanes whose distribution is published and installable. A lane listed here must
# not carry a disabled reason, because resolve_lane_runtime skips the
# installed-version observation entirely while that field is set: a stale reason
# hides a working install rather than reporting drift against it.
PUBLISHED = ("relay", "mneme", "plexus", "canon", "chorus", "accountable-surface")


def test_published_lanes_are_not_marked_package_disabled():
    for name in PUBLISHED:
        assert not LANES[name].package_disabled_reason, (
            f"{name} is published; its package_disabled_reason is stale, and "
            "while it is set the runtime never looks at what is installed")


def test_every_pip_lane_declares_a_release_version():
    """Structural, because a pinned literal per lane guards nothing useful.

    test_lanes used to assert LANES["index"].version == "2.10.0" and
    LANES["mneme"].version == "0.4.2". Those pins sat green while five lanes had
    drifted away from what PyPI actually carried: gather declared 1.6.1 against
    1.8.2, index 2.10.0 against 2.13.0, forum 1.13.0 against 1.14.0,
    calibrate-pro 1.1.0 against 2.0.0, articulate 0.2.0 against 0.3.0. A literal
    only proves the number has not changed, which is the opposite of what
    matters when resolve_lane_runtime compares it to the installed version by
    equality.

    Checking a declared version against the index needs the network, so it
    cannot live here. That is done at release time by installing each lane from
    PyPI and probing it. What this test can enforce is that every pip lane
    declares a version at all, in a shape the comparison will not mishandle.
    """
    for name, lane in LANES.items():
        if lane.kind != "pip":
            continue
        assert re.fullmatch(r"\d+\.\d+(\.\d+)?", lane.version), (
            f"{name} declares version {lane.version!r}, which is not a release "
            "number resolve_lane_runtime can compare")


def test_a_disabled_lane_states_a_reason_worth_reading():
    """An empty or bare reason reads as 'unavailable' with no way to act on it.

    lane_status hands this string to the operator verbatim, so it has to carry
    both halves: what is wrong, and what to do instead. That is checked as two
    sentences rather than by looking for particular words. Whether prose is
    useful to a human is not mechanically decidable, and a whitelist of phrases
    would fail a future reason that is perfectly clear and worded differently,
    which is the same brittleness that let the old version literals in test_lanes
    sit green through five real drifts.
    """
    for name, lane in LANES.items():
        reason = lane.package_disabled_reason
        if not reason:
            continue
        assert len(reason) > 40, f"{name}: disabled reason is too thin to act on"
        sentences = [part for part in reason.split(". ") if part.strip()]
        assert len(sentences) >= 2, (
            f"{name}: disabled reason is one sentence, so it states a problem "
            "without an alternative. Say what to run instead.")


def test_no_pip_lane_hides_an_extras_marker_in_its_install_name():
    """An extras marker there installs correctly and breaks version detection.

    installed_version() passes install_name straight to
    importlib.metadata.version, which does not accept "pkg[extra]". Putting the
    extra there is the obvious way to make a lane whose server needs an optional
    dependency install completely, and it silently costs the version comparison.
    accountable-surface is the lane that tempted this: its FastMCP entry needs
    the [server] extra, so it points at the stdlib-only server instead.
    """
    for name, lane in LANES.items():
        if lane.kind != "pip":
            continue
        assert "[" not in lane.install_name, (
            f"{name} declares install_name {lane.install_name!r}; "
            "importlib.metadata.version cannot resolve an extras marker")

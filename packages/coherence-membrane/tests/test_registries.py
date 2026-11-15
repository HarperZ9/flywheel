from __future__ import annotations

import pytest

from coherence_membrane.reconcile import Criterion
from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.registries import CriterionRegistry, PerceiverRegistry


def _crit(name="origin"):
    return Criterion(name, lambda form: Certificate(str(form), Verdict.VERIFIED, "origin-v1"))


def test_criterion_register_and_get_by_name_version():
    reg = CriterionRegistry()
    reg.register(_crit(), version="v1")
    assert reg.get("origin", "v1") is not None
    assert reg.get("origin", "v2") is None       # version-scoped
    assert reg.get("missing", "v1") is None


def test_perceiver_register_and_get():
    reg = PerceiverRegistry()
    reg.register("echo", lambda args: (args, str(args).encode()))
    fn = reg.get("echo")
    assert fn({"x": "1"}) == ({"x": "1"}, b"{'x': '1'}")
    assert reg.get("missing") is None


def test_criterion_version_collision_raises():
    """Registering a different criterion under the same (name, version) raises ValueError."""
    reg = CriterionRegistry()
    c1 = _crit("equals")
    c2 = _crit("equals")  # different object, same name
    reg.register(c1, version="v1")
    with pytest.raises(ValueError, match="version collision"):
        reg.register(c2, version="v1")


def test_criterion_reregister_same_object_is_ok():
    """Re-registering the IDENTICAL object under the same (name, version) does not raise."""
    reg = CriterionRegistry()
    c = _crit("equals")
    reg.register(c, version="v1")
    reg.register(c, version="v1")  # idempotent -- same object, should not raise

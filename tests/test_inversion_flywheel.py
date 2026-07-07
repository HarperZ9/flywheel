"""inversion flywheel falsifier — the active inverse loop: accelerate, but never beat the floor.

The reconcile's backward direction, driven as a self-directed loop that chooses the
next shadow. Two bounds: it ACCELERATES (skips uninformative shadows, reaches the
floor in fewer steps) and it is FLOOR-BOUND (reaches the same permanent floor as
passive on underdetermined domains — it cannot manufacture access to the null space).
"""
from harness.inversion_flywheel import (run_acceleration, run_floor_preservation,
                                        active_curve, passive_curve, acceleration_demo)


def test_active_loop_accelerates_by_skipping_uninformative_shadows():
    a = run_acceleration()
    assert a["accelerated"] is True
    assert a["active_to_floor"] < a["passive_to_floor"]   # strictly fewer shadows
    assert a["same_floor"] is True                        # ...to the same answer


def test_flywheel_cannot_beat_the_null_space_floor():
    f = run_floor_preservation()
    assert f["all_floors_preserved"] is True
    # consciousness and dream keep their permanent floor under OPTIMAL active sensing
    floors = {d["name"]: d["active_floor"] for d in f["per_domain"]}
    assert floors["access_vs_phenomenal"] == 2 and floors["manifest_latent"] == 4


def test_active_is_never_slower_than_passive():
    assert run_floor_preservation()["all_faster_or_equal"] is True


def test_greedy_skips_the_redundant_duplicate():
    # the acceleration demo streams a duplicate of bit0; the active loop must not
    # spend a cycle on it while an informative shadow remains
    a = active_curve(acceleration_demo())
    assert a == [8, 4, 2, 1, 1]     # collapses to 1 by step 3, then the dup adds nothing

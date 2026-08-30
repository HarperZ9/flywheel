"""Pin the externalization guard form and state B0's honest null.

The externalization form is a non-self-authored check refuting a cheat that a
self-authored check accepts. B0 v1 still has one hidden tier, so it does not
prove resistance to a candidate overfitting that tier's exact inputs.
"""

from harness.externalization_ablation import run_all_domains


def test_externalization_form_covers_every_domain(tmp_path):
    result = run_all_domains(tmp_path)
    assert result["coverage"] == 1.0
    assert result["all_refutations_executed"] is True
    assert result["caught"] == result["n_domains"]

"""Protocol parameters from SPEC.md section 0.2.

Every value is a design target (DT) from the appendix, a placeholder the
appendix sets (PH-A), a placeholder the specification adds (PH-S) or a
placeholder the charter or clause adds (PH-C). None is
a measurement. Durations are seconds. A demo may override a value; the
override is then a demo value (DEMO) and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace

MIN = 60
HOUR = 3600
DAY = 86400
STAGE_L = "L"  # logging, alerts, notice, audit; no remote stop/throttle
STAGE_F = "F"  # full fail-closed governance (throttle, halt, fail-closed)

HONEST_HARDWARE_LIMIT = {
    "no_physical_on_chip_lock": True,
    "summary": (
        "No physical on-chip lock exists yet. On Windows with a TPM, device signing "
        "(ECDSA P-256) and TPM2_ReadClock run on the TPM; monotonic counter, time floor, "
        "and tamper input stay in software until dedicated hardware is attached."
    ),
}


@dataclass(frozen=True)
class Params:
    t_tamper_detect: int = 1 * HOUR          # PH-A targets table
    renewal_validity: int = 7 * DAY          # PH-A, inside T_SILENT
    time_allowance: int = 72 * HOUR          # PH-A, inside T_SILENT
    t_effect: int = 15 * MIN                 # PH-A targets table
    t_failclosed_log: int = 1 * MIN          # DT targets table
    false_halt_rate_per_10k_dy: float = 1.0  # PH-A targets table
    n_seats: int = 7                         # PH-A
    k_order: int = 4                         # PH-A
    k_renew: int = 4                         # PH-S
    k_restore: int = 4                       # PH-S
    k_remove: int = 5                        # PH-A
    max_per_region: int = 2                  # PH-C, CHARTER.md Art. 3(g)
    min_signer_regions: int = 3              # PH-C, CHARTER.md Art. 3(h)
    t_halt_max: int = 7 * DAY                # PH-A halts, PH-S throttles
    t_converge: int = 24 * HOUR              # PH-A
    t_record: int = 1 * MIN                  # DT
    t_alert: int = 1 * HOUR                  # DT
    t_notify_hw: int = 4 * HOUR              # DT
    t_notify_other: int = 24 * HOUR          # DT
    t_esc_eval_handoff: int = 24 * HOUR      # DT
    t_esc_eval_report: int = 72 * HOUR       # DT
    t_esc_gov_referral: int = 72 * HOUR      # DT
    t_esc_gov_decision: int = 7 * DAY        # DT
    t_vote: int = 4 * HOUR                   # PH-S
    t_appeal: int = 7 * DAY                  # PH-A
    t_heartbeat: int = 10 * MIN              # PH-S
    missed_intervals: int = 3                # PH-S
    t_epoch: int = 24 * HOUR                 # PH-S
    t_lapse_warn: int = 72 * HOUR            # PH-S
    t_halt_notice: int = 1 * HOUR            # PH-S
    logs_min: int = 2                        # PH-S
    logs_listed: int = 3                     # PH-S
    k_witness: int = 3                       # PH-S
    n_witness: int = 5                       # PH-S
    n_time: int = 3                          # PH-S
    k_time: int = 2                          # PH-S
    time_tol: int = 10                       # PH-S
    rate_throttle_window: int = 1 * HOUR     # PH-S: 1 change per cluster per window
    rate_halt_window: int = 30 * DAY         # PH-S
    rate_halt_max: int = 2                   # PH-S: halts per tag per window
    rate_source_per_hour: int = 60           # PH-S
    landmarks_min: int = 3                   # PH-S
    t_refuse: int = 6 * HOUR                 # PH-S
    t_cosign: int = 1 * MIN                  # PH-S
    t_poll: int = 5 * MIN                    # PH-S
    loc_interval: int = 6 * HOUR             # PH-S
    # Added after the reviews of 25 September 2026 (README.md Findings P48, P41, P55).
    throttle_min: int = 10                   # PH-S: lowest throttle level, percent
    drift_ppm: int = 100                     # PH-S: timer drift bound for forward time moves
    maint_window: int = 8 * HOUR             # PH-S: longest logged maintenance window
    maint_rate: int = 4                      # PH-S: windows per device per 30 days
    stage: str = STAGE_F                     # Stage L (log-only) or Stage F (fail-closed)
    demo_overrides: tuple = field(default=())

    @property
    def t_silent(self) -> int:
        return self.renewal_validity + self.time_allowance

    @property
    def t_missed(self) -> int:
        return self.t_heartbeat * self.missed_intervals

    def with_demo(self, **values) -> "Params":
        """Return a copy with demo values. The copy remembers which ones."""
        known = {f.name for f in fields(self)}
        unknown = set(values) - known
        if unknown:
            raise KeyError(f"unknown parameters: {sorted(unknown)}")
        tags = tuple(sorted(set(self.demo_overrides) | set(values)))
        return replace(self, demo_overrides=tags, **values)


KIND = {
    "t_tamper_detect": "PH-A", "renewal_validity": "PH-A", "time_allowance": "PH-A",
    "t_effect": "PH-A", "t_failclosed_log": "DT", "false_halt_rate_per_10k_dy": "PH-A",
    "n_seats": "PH-A", "k_order": "PH-A", "k_renew": "PH-S", "k_restore": "PH-S",
    "k_remove": "PH-A", "t_halt_max": "PH-A", "t_converge": "PH-A", "t_record": "DT",
    "t_alert": "DT", "t_notify_hw": "DT", "t_notify_other": "DT",
    "t_esc_eval_handoff": "DT", "t_esc_eval_report": "DT", "t_esc_gov_referral": "DT",
    "t_esc_gov_decision": "DT", "t_vote": "PH-S", "t_appeal": "PH-A",
    "max_per_region": "PH-C", "min_signer_regions": "PH-C",
}


def kind(name: str) -> str:
    """Kind label for a parameter; everything not listed is PH-S."""
    return KIND.get(name, "PH-S")

"""The prototype's findings, P1 to P18 and P40 to P56, for the final follow-up tables.

Each finding is stated in full where it arises (README.md, the drills report
or a module docstring). This list restates each one with what it changes.
"""

FINDINGS = [
    ("P1", "README 3.1; crypto.py", "The Windows TPM provider offers ECDSA P-256 and no Ed25519, "
     "while SPEC.md 0.1 names Ed25519 for every signature",
     "Every signature record names its algorithm; SPEC 0.1 should list algorithms per role "
     "and let device keys use what the root of trust offers", "Yes"),
    ("P2", "README 3.2; nvidia.py", "The build request asked for GPU power and utilization in "
     "the heartbeat; SPEC 3.3 and the appendix bar both",
     "Conforming heartbeats carry no usage field; a banded telemetry profile exists, marked "
     "non-conforming and off by default; the author decides whether any usage band belongs "
     "in the protocol", "Yes"),
    ("P3", "Drills report 2", "T_SILENT adds renewal validity and the 72-hour allowance, but "
     "the device rules make them alternatives: a fully offline device stopped at 72 hours on "
     "time lapse, and the longest run came from a device that hid its heartbeats while still "
     "receiving roots: validity plus one epoch",
     "Restate T_SILENT as validity plus T_EPOCH for a device that hides only its heartbeats, "
     "and 72 hours for a device that is fully offline", "Yes"),
    ("P4", "README 3.3; shim.py check 10", "An order sits in LOGS_MIN logs at different "
     "indices, so the single log_index fields for the criterion and the dependent notice "
     "cannot be checked as written",
     "Reference entries by fingerprint and compare positions per log, as the prototype does",
     "Yes"),
    ("P5", "README 3.4; signals.py", "Proof-class signals (clone, split view, time "
     "malfeasance) have no stated role in the convergence rule",
     "The prototype does not count them; the spec should say whether a proof counts as a "
     "hardware and network signal", "Yes"),
    ("P6", "Drills report 1", "No device self-check period is set, and the recheck can "
     "measure T_FAILCLOSED_LOG only from the device's detection time",
     "Set a self-check period and state which interval T_TAMPER_DETECT covers", "Yes"),
    ("P7", "Drills report 4; monitor.py", "The lapse warning keys on devices missing from two "
     "roots; a cut renewal path leaves devices in good standing and draws no warning",
     "Warn from the renewal epoch each heartbeat reports; the prototype does, and the "
     "drills report gives the warning lead", "Yes"),
    ("P8", "Drills report 4", "After a correlated lapse, service waits for the next daily root",
     "Seats re-deliver the latest root, or issue one out of cadence, when a path returns",
     "Yes"),
    ("P9", "README 3.5; timesrc.py", "SPEC 6.1 asks for servers run by 2 parties but its "
     "quorum rule does not require the agreeing replies to span 2 parties",
     "The prototype requires 2 parties inside the agreeing set", "Yes"),
    ("P10", "README 3.5; timesrc.py", "One chained pass proves a lie only when an honest reply "
     "follows the liar", "Query the server list twice so every server precedes and follows "
     "every other; SPEC 6.1 should say so", "Yes"),
    ("P11", "README 3.6; alerts.py", "Widening each timestamp by TIME_TOL (10 s) leaves a 60 s "
     "record clock MET only for gaps up to 40 s and UNVERIFIABLE from 40 to 80 s",
     "State the interaction, or tighten TIME_TOL for the record clock", "Yes"),
    ("P12", "README 3.1; HARDWARE-DEVKIT.md", "The TPM NV counter needs owner authorization "
     "Windows holds, so the counter and tamper switch run in software on this PC",
     "The dev kit needs a secure element with a counter and tamper input it controls", "Yes"),
    ("P13", "README 3.5; device.py", "After a power cycle the prototype stops covered work "
     "until a fresh quorum, stricter than SPEC 6.2, which lets committed work finish",
     "Keep as a stated deviation or implement the finish-committed-work allowance", "Yes"),
    ("P14", "Demo step 2", "The demo restarts halted work under a new name and the device "
     "cannot tell, which confirms SPEC Finding S5 on live processes",
     "The halt stays an operator duty the clause binds; the cluster throttle is the backstop",
     "No; the clause's drafters decide"),
    ("P15", "README 5; device.py", "An editable reference set let one removal fail every "
     "device running a build", "Append-only set; the device checks the build installed "
     "under the set in force at install", "Yes, done"),
    ("P16", "README 5; seats.py", "The roster check allowed one seat both flags and let "
     "frontier-host nationals fill reserved seats", "Both checks added; check 3 ignores a "
     "doubly flagged seat", "Yes, done"),
    ("P17", "README 5; seats.py, shim.py", "Caps counted states only, so one region could "
     "fill a quorum", "Region cap and a 3-region signer span for rosters, orders and "
     "renewals", "Yes, done in part"),
    ("P18", "README 5; signals.py", "One hard signal counted toward convergence",
     "Only soft signals count", "Yes, done"),
    ("P40", "README 3.5; devtime.py", "A time chain recorded once could be replayed after "
     "every power cycle, so a silent device ran past T_SILENT on a day-0 chain",
     "Chains start from the device's own nonce in the same boot; a stored time floor "
     "bounds the first quorum after boot (SPEC S43)", "Yes, done"),
    ("P41", "README 3.5; devtime.py", "A colluding quorum 8 days ahead of a running timer "
     "was accepted and lapsed the renewal at once", "While the boot id holds, a quorum "
     "more than TIME_TOL plus DRIFT_PPM of elapsed time ahead is refused and reported "
     "(SPEC S44)", "Yes, done"),
    ("P42", "README 3.5; timesrc.py, proofs.py", "Quorum members could sit 2 x TIME_TOL "
     "apart; LOGS_MIN counted log ids and ignored operators and jurisdictions; the view "
     "commit on a refused order was undocumented", "Pairwise spread within TIME_TOL; "
     "LOGS_MIN counted over operators and jurisdictions; the commit is documented as safe",
     "Yes, done"),
    ("P43", "README 3.7; monitor.py, device.py", "A registered device that never reported "
     "was never missed, and a rolled-back chain head with an intact counter ran on",
     "Silence counts from registration; boot_check and the desk treat a broken chain as "
     "a hard signal (SPEC S40)", "Yes, done"),
    ("P44", "README 3.7; gossip.py", "Gossip caught only equal-size forks and could not "
     "prove them", "Heartbeats carry the log's checkpoint signature; the desk checks "
     "neighbouring sizes with a consistency proof and emits signed evidence (SPEC "
     "S41)", "Yes, done"),
    ("P45", "README 3.8; roster_change.py", "Four seats could replace the other three "
     "keys, and devices never took a roster from the logs", "Removal needs K_REMOVE and a "
     "logged cause; devices adopt a roster only when it is proven in LOGS_MIN logs (SPEC "
     "S42)", "Yes, done"),
    ("P46", "README 3.8; devsupport.py", "A device accepted a renewal valid for ten years",
     "Refuse a span over RENEWAL_VALIDITY or a start after working time plus TIME_TOL "
     "(SPEC S45)", "Yes, done"),
    ("P47", "README 3.8; world.py", "No code logged a silent seat after T_REFUSE",
     "The desk logs a seat-silence entry per root after T_REFUSE; drill 12 reports it",
     "Yes, done"),
    ("P48", "README 3.3; shim_rules.py", "A throttle at level 0 stopped all work outside the "
     "halt rules, and a malformed level broke every later heartbeat", "Check 1 takes an "
     "integer level from THROTTLE_MIN to 99 before storing; enforcement faults never stop "
     "a heartbeat (SPEC S46)", "Yes, done"),
    ("P49", "README 3.3; shim_rules.py", "Check 10 accepted any earlier entry as the notice",
     "The notice must be a seat-signed dependent notice for the same cluster, covering the "
     "tags and the expiry (SPEC S49)", "Yes, done"),
    ("P50", "README 3.3; shim_rules.py", "Any value in renews skipped RATE_HALT and could end a "
     "halt on other tags", "A renewal names an order in force with the same scope and "
     "cites a logged governance decision (SPEC S47)", "Yes, done"),
    ("P51", "README 3.3; shim.py", "A lift did not cancel a halt still in its notice lead",
     "A lift removes pending orders too and the device refuses the lifted id (SPEC "
     "S48)", "Yes, done"),
    ("P52", "README 3.3; proofs.py, shim.py", "A stripped bundle field raised an exception, "
     "so no refusal was signed", "Any malformed input becomes a signed refusal at the "
     "check where it surfaced (SPEC S50)", "Yes, done"),
    ("P53", "README 3.9; location.py", "Measurement records named no time, region_check named "
     "no device, a negative delay moved a far device near, heartbeats never carried a "
     "location, and a thin region read FAIL", "Records carry measured_ms; checks bind device "
     "and age; negative delay raises; the heartbeat carries the set; a thin region reads "
     "UNVERIFIABLE (SPEC S51)", "Yes, done"),
    ("P54", "README 5; drills report 5", "Four seats could revoke the other three keys "
     "for compromise and hold every vote", "CHARTER.md Article 9 in code: revocation by "
     "request, recovery-key repudiation or K_REMOVE; re-enrolment by recovery key; the "
     "clone basis and the reserve fallback are not built", "Yes, done in part"),
    ("P55", "README 5; maintenance.py", "Every chassis opening was a hard signal needing "
     "K_RESTORE seats", "A logged maintenance window turns a tamper event into a "
     "restoration by inspection and attestation, with no seat vote", "Yes, for the "
     "prototype; the spec's owners decide the rule"),
    ("P56", "README 5; drills report 5", "Under draft 0.1 a listed firmware update drops "
     "every updated device out of the next root", "A stable device identity with a "
     "per-firmware alias key; not built here", "Yes; not yet done"),
]

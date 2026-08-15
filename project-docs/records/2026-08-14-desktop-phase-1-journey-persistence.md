# Desktop Phase 1 Journey persistence acceptance.

**Date:** 2026-08-14.
**Verdict:** PASS for the bounded Phase 1 persistence and custody-export scope.
**Source boundary commit:** `7d3ace27de92a775e170114c83b2a529488c6c00`.
**Source boundary tree:** `1f6a0d05e87e7238912bd5b45a32fa688e6de9ff`.
**Initial implementation commit:** `744a74d2eb582d4e9e848dc4618228cdccae0933`.
**Initial implementation tree:** `1c34d0039fd2f67512345abd5056bb9a4818b98b`.
**Reviewed code-fix commit:** `94392b6d1f5faced8c8eba6fc60cd281d2611dcc`.
**Reviewed code-fix tree:** `25c866b651626afd13d5e06bec8a28cfa7a0ebf1`.

This record accepts the Journey-v2 event store, public transport, exact-grant
custody export, and restart recovery. It also accepts offline clean-copy
recheck. It does not widen the legacy v1 packet contract.

## Bound material.

The deterministic acceptance packet used five concluded Journey events. Its
unanchored structural verdict was `MATCH`, while its overall verdict and
authenticity state remained `UNVERIFIABLE`. Supplying the exact manifest digest
changed the overall and rehash-resistance verdicts to `MATCH`.

- Fixture: `a17b404f7b967a5e0558842b1fe5ed44b7c95f3aac3246e29b44d2c94be5f5ee`.
- E2E test: `c68233a75eaf3351ae67615fd696992178efece7dbe73bc6e035c3eada989d1e`.
- Packet test: `69363872cb9f5bdec7360166cf5013f4eaa81c787af7ef59b8a3b0961326c776`.
- Export test: `dd8f8b0a6359e8f42ae9c02da0ecbbe999a382dbe7a74994c7c4b687e500b553`.
- Transaction test: `8ce328bbb2d6df5749f58bb09d5ce6760e14e407eaa8ed4d76e272c7152961bb`.
- Packet manifest: `sha256:54f028b9e7359e9db5f5ea64122fd27b66b87b544f92e60701d4795a81cc05d6`.
- Packet source head H0: `b34db23c5a3e477ccf08a74be0a794129b0e93ed87a0e2721fc55306edd84bd3`.
- Packet source projection P0: `bac7b716e8cf4401284e11515ec185fe17580916718c2151318a1c9bd8858163`.

The packet criterion schema is exactly `flywheel.evidence-packet/v1`, with the
closed-union profile `flywheel.evidence-journey-custody/v2`. The legacy-only
`verify_journey_packet` entry point rejects this profile. The regression test
`test_legacy_v1_packet_verifier_rejects_v2_profile` freezes that separation.

## Acceptance denominators.

The public flow made 43 authenticated route calls: 17 Journey calls and 26
prepare or approve-once grant calls. The 17 Journey calls contained 13 mutation
attempts, three lens resumes, and one list. The accepted log contains exactly 12
events through final head H1. It has one intake, one claim, four stages, two
check requests, three check outcomes, and one export.

The check denominator is 2 requested and 2 terminal. Outcomes were 1 blocked,
1 completed, 0 failed, 0 cancelled, and 0 unclosed. The blocked Python path made
0 candidate reads, runner calls, child processes, receipts, provider calls, or
network calls. The admitted data-only path made exactly 1 call to the injected
deterministic runner after its request passed through the authenticated route.

The export crash denominator is 9 injected windows. Five cover export phases
from grant consumption through response. Three cover event fsync, head
replacement, and Journey directory fsync. One covers the durable quarantine
move before its final phase seal.
Every case converged to one exact packet and one exported event. The recovery
denominator is 7: four phase-completion cases, two competing-head quarantine
cases, and one clean no-op recovery. The two-export race denominator is 2: one
same-target race and one different-target race. Each race produced one
`MATCH`, one `HEAD_CONFLICT`, one exported event, and no overwritten neighbor.

The fixture counters all matched: acknowledged loss 0, duplicate logical event
0, silent overwrite 0, unclosed check request 0, blocked 1, completed 1, failed
0, and cancelled 0.

## TDD and verification record.

The initial missing-service RED follows.

```text
python -m pytest tests/test_journey_packet_v2.py tests/test_journey_export.py tests/test_journey_persistence_e2e.py -q -ra
exit 1: three collection errors for missing Journey packet/export modules
```

The public integration RED follows.

```text
python -m pytest tests/test_grant_route.py tests/test_journey_route.py -q -ra
exit 1: export grant data refs were incomplete and the export route returned 409
```

The accepted commands and observed exits follow.

- Packet tests: exit 0, 18 passed.
- Export and transaction tests: exit 0, 34 passed.
- Acceptance E2E: exit 0, 1 passed.
- Legacy packet and transport command: exit 0, 183 passed.
- Explicit evidence, Journey, operation, and grant list: exit 0, 557 passed and 2 platform skips.
- File gate: exit 0, 69 grandfathered, 0 new, 0 grown.
- Verifier closure: exit 0, 51 modules from 26 entry points, clean.
- Claim-language gate: exit 0, 20 public surfaces, clean.
- Public-instruction gate: exit 0, no new public leak.
- Initial implementation full suite: exit 0, 4,810 passed and 23 expected skips.
- CLI gate: exit 0, `verdict=PASS`, `rewitness=MATCH`.
- Procedure writing gate: exit 0, no hard violation.

The full suite emitted one existing Pillow deprecation warning. Its skips were
platform or optional-checkout capability skips. No test skipped the new Journey
packet, export transaction, recovery, route, or acceptance behavior.

## Durability boundary and rollback.

The service serializes Journey export admission and the canonical packet target.
It consumes the exact grant and persists a digest-closed private transaction.
It builds in service-owned staging, verifies, and publishes by absent-target
rename. It appends the exported event by CAS at H0. It acknowledges after the
committed transaction is flushed. Recovery requires an exact consumed and
digest-matched private grant record. A competing head moves only the exact
service-owned target to private quarantine. A durable intermediate phase makes
the move recoverable before the final quarantine seal.

Rollback means reverting the commit titled `test: accept durable journey
persistence`. Do not delete Journey events, export transactions, packets, or
quarantine material during rollback. The legacy v1 verifier and route remain
unchanged. Reverting the new route integration removes export admission without
rewriting accepted v1 bytes.

## Does not prove.

This acceptance proves the tested custody structure and bounded durable state
transitions. It does not prove claim correctness, evidence completeness, or
general execution containment. It does not prove origin authenticity, provider
behavior, network isolation, or filesystem durability outside the tested
boundaries. The packet binds pre-export H0 and P0, not final exported H1.
Checker-source drift is separate from carried structure and remains
`UNVERIFIABLE` across versions. It contains no signed author identity and no provider trace. No provider, model,
endpoint, network service, live Python candidate, or subprocess checker ran.
This record does not prove Phase 2 behavior, general release readiness, package
publication readiness, or production deployment readiness.

# Windows contention test contracts

The browser process tests separate an admission race from a deliberate lock
deadline miss. Both retain the durable reservation, session cap, and exactly one
driver effect. A child reports only `JourneyLockBusy` as a typed busy result;
unexpected exceptions remain child failures with decoded stdout and stderr.
After both original callers settle, a busy caller may make one explicit replay
with its original request ID. This is a test of the known pre-dispatch refusal,
not a transport retry after an uncertain send. The crash-after-effect test still
requires an admitted, delivery-unknown replay with no second effect.

The continuation tests require twelve actual callers, eleven failed real outer
lock attempts while the owner is held, one create, one preview binding, and one
Journey. Their controlled clock applies only while acquiring that outer lock.
Grant and Journey acquisitions inside the critical section keep their real
deadlines. The separate expiry case still requires typed refusals before any
create mutation and explicit replay after the owner settles.

The ten-second fixture watchdog is unchanged. If it expires, its failure records
recent phases, completion counts, and thread stack locations without frame locals
or request payloads. A worker's own exception is propagated without relabeling it
as a watchdog timeout.

These changes do not establish the slow phase behind the original Windows CI
continuation timeout. The executor waits for its workers during teardown, so the
reported timeout does not by itself establish a permanent deadlock. A controlled
delay across successful create and append phases reproduced that timeout while
all twelve callers later returned successfully and durable readback showed one
Journey and one preview binding. The watchdog continues to reject that delay;
the new evidence identifies the pending phase instead of discarding the failure.

Focused checks:

```sh
python -m pytest tests/test_browser_admission_process.py tests/test_native_continuation_start_contention.py tests/test_continuation_contention_probe.py -q
```

These checks do not replace the full CI suite or prove hosted runner latency.

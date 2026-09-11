# Waiting for durable agent completion

The nonstream agent route waits for the existing durable operation. A temporary
Journey lock failure must not discard that wait or dispatch the action again.

The terminal wait retries only the typed `STORE_BUSY` read failure, using the
operation event condition to wait between attempts. One monotonic deadline
covers every attempt; notifications do not extend it. Existing per-read store
acquisition bounds remain in force. Persistent contention ends with `STORE_BUSY`;
a readable operation that remains nonterminal keeps the existing timeout error.
Other store, integrity and authorization errors propagate immediately.

Completed, failed and cancelled snapshots remain terminal observations. The wait
helper neither controls the worker nor reauthorizes, cancels or resubmits it.
Grant consumption, operation identity and the durable result stay unchanged.

A synthetic control holds a real Journey lock across the first nonstream read,
then releases it when the waiter yields. The action dispatches once and returns
its original durable result. Deadline, persistent-contention, nonbusy-error and
cancellation controls cover the failure boundaries.

The triggering CI log reported `STORE_BUSY` but did not identify the lock holder
or acquisition site. The synthetic control establishes the recovery defect; it
does not establish the original runner's scheduling cause. This change covers
the terminal wait. Separate terminal-result hydration still uses its existing
read contract.

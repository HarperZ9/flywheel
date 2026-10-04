"""monitor_gate -- the admission gate a text monitor passes before its verdicts count.

`flywheel monitor gate <adapter>` runs a monitor over a frozen, hash-pinned set
of parity-product items: 892 known-invisible items, where the computation
happened with nothing in the trace and a NO is false assurance; 892
known-visible items, where the full working is in the trace and the correct
verdict is NO; and 892 known-visible parity items, where the trace shows the
parity check and the correct verdict is YES. Planted controls run on every gate run. The result is a signed
flywheel.receipt/v4 that a stranger re-derives with `flywheel monitor
gate-verify`. See docs/MONITOR-GATE.md for what an admission does and does not
show.
"""

# Swarm fan-in: recheck and size

A swarm runs up to 8 subagent children and seals one fan-in receipt: each
child's run receipt, the completed and verified quorum counts, and a swarm
certificate that hashes every child's chain head and accepted flag.
`harness.subagent_fanin.recheck_swarm_receipt` re-derives all of that offline
from the children the receipt carries and returns MATCH, or DRIFT with every
field that failed to re-derive. A child's own chain is discarded when the swarm
seals, so the recheck works from the chain heads the receipt holds.

## How the cost grows

Measured with `scripts/measure_swarm_fanin.py` on synthetic children (receipts
built in memory), 15 runs per size, sizes interleaved, one Windows 11 desktop:

| Children | Seal, median | Recheck from file, median (p10 to p90) |
|---:|---:|---:|
| 8 | 0.9 ms | 7.9 ms (6.5 to 9.1) |
| 64 | 1.4 ms | 8.3 ms (7.1 to 10.4) |
| 512 | 5.7 ms | 9.6 ms (8.1 to 12.7) |

Recheck at 512 children costs 1.15 times what it costs at 64. Flipping one
child's accepted flag or chain head in a saved 512-child receipt is reported
as DRIFT, and the quorum rules hold at that size: `any` needs 1 child,
`majority` 257, `all` 512.

## Why the cap is still 8

The fan-in is not what limits swarm size. Every child is a process, and a
swarm launches all of its children at once, so a larger cap first needs a
limit on how many children run at the same time, carried through the restart
and gateway paths. Until that lands the cap stays at 8.

These numbers measure hashing and arithmetic on one machine. The cost of
running many real child processes is a separate measurement.

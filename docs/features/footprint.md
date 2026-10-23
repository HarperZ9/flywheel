# Footprint and startup

How big Flywheel's terminal harness is, how fast `flywheel code` is ready for
typing, and how much memory it holds at that point. Measured with
`scripts/measure_footprint.py` on flywheel-verify 1.8.0 from PyPI in a fresh
virtual environment, Python 3.12.10, Windows 11, one desktop, 15 October 2026.
Ten runs per metric with cold and warm runs interleaved.

| Metric | Median | p10 to p90 |
|---|---:|---:|
| Installed size (the package, no dependencies) | 10.4 MB | |
| `flywheel --version` | 0.11 s | 0.09 to 0.14 s |
| Time to the `flywheel>` prompt, cold (no bytecode cache) | 0.40 s | 0.34 to 0.61 s |
| Time to the prompt, warm | 0.29 s | 0.23 to 0.35 s |
| Memory at the prompt, warm (working set) | 30.4 MB | 30.1 to 30.5 MB |
| Memory at the prompt, cold | 31.6 MB | 31.3 to 32.2 MB |

How it is measured: `flywheel code` starts with its model backend pinned to a
scripted stub on loopback, so no model server is probed or called, and the
clock stops when the prompt appears. The process is the Python interpreter
itself with the environment's packages, not the console-script launcher, so
the memory reading is the harness. "Cold" means the bytecode cache was
deleted; the operating system's file cache was warm in every run.

An earlier full run on the same build had one cold start at 2.97 s, which put
that run's cold p90 at 2.97 s and its cold spread wider than its median. Cold
start on this machine is noisy enough that a single slow run is possible; the
warm figures matched within 0.01 s.

Scope: one machine on one day. Startup runs against a stub, so a real
provider's answer time, which dominates a real first turn, is excluded. The
page compares Flywheel builds with each other. A side-by-side run against other
harnesses needs a terminal driver, which is the next addition to this suite.

## Gating a startup change

`scripts/ab_startup.py` runs two builds in alternating order (20 pairs by
default). It accepts a change when the 95% bootstrap interval of the warm time
to prompt lies below zero and every neighbor (cold time, memory, `--version`
time) stays within 5% or has an interval that reaches zero. Every
experiment, accepted or refused, goes into a hash-chained record.

On four planted changes to 1.8.0 it refused a comment-only change, a 50 ms
import delay (cold start +43 ms, interval +18 to +68 ms) and a change holding
20 MB at import (+20.3 MB). It also refused a real import deferral worth about
15 ms by import timing, because 20 pairs on this machine resolve about 50 ms;
the accept path has been exercised only on synthetic numbers so far.

# Is verification keeping up with what ships?

`flywheel verify-share` shows, week by week, how much work shipped and how much of it was checked. It also shows what the checking cost. Use it to see when agents produce changes faster than anyone verifies them.

```
flywheel verify-share items.jsonl
flywheel verify-share prs.json --github [--family-from repo|prefix] [--json]
```

## What it reports

Every shipped item takes one of three routes:

| Route | Meaning |
| :- | :- |
| machine | Re-derived against an independent check |
| person | A person checked it |
| unchecked | Neither |

For each ISO week (Monday to Sunday), the report gives the number of items, their total size, and the share of that size on each route.

**The flag.** A week is flagged when the unchecked share has risen two weeks running and output grew over the same two weeks. The command then exits 1, so a scheduled job can alert on it.

**The cost-to-verify meter.** For each task family, the meter lists:

- the items on each route;
- the unchecked share, with a 95% Wilson interval;
- reviewer minutes summed over person-checked items;
- how many person-checked items had minutes logged at all.

A family with more than half its items unchecked is marked `hold-on-completion`. Its work should wait for a check before it counts as done.

## Inputs

Shipped-item records, one JSON object per line:

```json
{"schema": "flywheel.shipped-item/v1", "id": "run-42", "shipped_at": "2026-09-14T10:00:00Z",
 "family": "docs", "route": "person", "size": 120, "reviewer_minutes": 15}
```

You can give `lane` (`A`, `H` or `UNVERIFIABLE`, as on a routed receipt) in place of `route`. Size is any whole-number measure of output you choose, such as lines changed.

For GitHub, save merged pull requests with `gh pr list --state merged --json number,title,mergedAt,additions,deletions,author,reviews,statusCheckRollup`. A pull request counts as person-checked when someone other than its author approved it. It counts as machine-checked when every reported check passed and at least one ran. Anything else is unchecked. Size is lines added plus lines deleted. GitHub records no review time, so minutes stay empty. To combine repositories, add a `repository` field to each pull request; the family then follows the repository.

## First reading: our own repositories, last month

We ran it on 832 pull requests merged across 20 of our repositories between 24 August and 3 October 2026.

| Week | Pull requests | Lines changed | Machine | Person | Unchecked |
| :- | :- | :- | :- | :- | :- |
| 2026-W35 | 76 | 255,764 | 0.90 | 0.00 | 0.10 |
| 2026-W36 | 209 | 206,849 | 0.82 | 0.00 | 0.18 |
| 2026-W37 | 172 | 311,403 | 0.98 | 0.00 | 0.02 |
| 2026-W38 | 88 | 146,799 | 0.99 | 0.00 | 0.01 |
| 2026-W39 | 72 | 327,294 | 1.00 | 0.00 | 0.00 |
| 2026-W40 | 215 | 641,167 | 0.96 | 0.00 | 0.04 |

No week was flagged. The usefulness bar set before this work asked for at least one flag on a stretch a person agrees was under-checked. With no flag, that bar is not met. Output nearly doubled from W39 to W40 while the unchecked share stayed under 0.05, so the flag stayed quiet.

Three things stand out:

- No pull request had an approval from a second person. Every check was a machine check or none.
- One repository had 11 of 40 pull requests unchecked, nearly all in W35 and W36, where its pull requests show no passing check. Its unchecked share for the month is 0.28 [0.16, 0.43].
- Counting passing CI as a machine check is generous. A docs-only change passes CI without CI testing anything it says. Read the machine share here as an upper bound on verified work.

## What it does not show

A route records which kind of check an item went through. It does not show the check was right. Shares depend on the size measure each source reports. Reviewer minutes are self-logged, and once people see the meter, they may log toward it.

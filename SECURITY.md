# Security policy

## Supported versions

| Version | Fixes |
|---|---|
| 2.x | Security fixes and all other fixes, in the next release |
| 1.9.x | Security fixes only, until 2027-02-12 (90 days after the 2.0.0 release) |
| 1.8.x and older | None. Upgrade to 2.x or to the latest 1.9.x |

`flywheel --version` prints the version you have. `flywheel update` says
whether a newer release exists. The rule for which releases get fixes is on the
[versioning page](docs/VERSIONING.md), and the changes between 1.x and 2.0 are
on the [migration page](docs/MIGRATING-2.0.md).

## Reporting a vulnerability

Private vulnerability reporting is enabled on this repository. Open a private
report at https://github.com/HarperZ9/flywheel/security/advisories/new. Only
the maintainer can read it.

Do not put the details of a vulnerability in a public issue, a pull request or
a discussion.

A useful report has:

- the Flywheel version (`flywheel --version`) and the operating system;
- the command, request or file that shows the problem;
- what you expected and what happened;
- whether the problem needs a local account on the machine, a network position
  or a crafted file.

Leave API keys, tokens and private data out of the report. `flywheel doctor
--json` prints provider keys by name only and is safe to attach.

## What to expect

Flywheel is maintained by one person. The maintainer reads a report, replies
in the advisory thread and works on a fix there. No response time is promised.
A fix ships in a release, and the changelog entry names the reporter if the
reporter wants that. Public description follows the fix or a date agreed with
the reporter. The rule is on the
[coordinated disclosure page](docs/rules/coordinated-disclosure.md).

## Scope

In scope: the `flywheel-verify` package, the `flywheel` command, the local
gateway and model server, the coding session and its sandbox, the receipt,
ledger and bundle verifiers, the Windows installer, and the plugins and
extensions built from this repository.

Out of scope: a hosted model provider's own service, and a problem that needs
an attacker who already controls the user's account on the machine. If you
are unsure, report it.

No bug bounty is offered.

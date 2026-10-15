# Flywheel 1.8.0

`flywheel setup` connects a model in one step, and `flywheel code` now reaches
models on Azure OpenAI, Amazon Bedrock and Google Vertex AI as well as the
providers it already knew. The agent can search the web, run up to four
read-only subagents at once, keep short notes for a project across sessions,
and run background jobs whose output streams and stops on Linux and macOS as
well as Windows. Plugins install from marketplaces, hooks cover eleven events
including permission decisions, and `flywheel update --apply` upgrades a pip
install in place. Every new tool call goes through the same permission mode,
rules, pre-action monitor and hash-chained ledger as the rest of the session.

## Behaviour changes to check before you upgrade

- **`flywheel doctor` counts keys stored in the OS credential store**, reported
  by name, not only keys in the environment.
- **Plan mode refuses `remember`** and edit mode allows it, like a file write.
- **A PermissionRequest hook can answer in your place.** With no such hook,
  nothing changes.

## Connect and reach

- `flywheel setup` lists what is connected and stores a provider key, read
  without echo, in the OS credential store; Flywheel never writes a key to a
  plain file. (#398)
- Azure OpenAI, Amazon Bedrock (requests signed with AWS Signature Version 4,
  checked against AWS's documented example) and Google Vertex AI backends, on
  when their settings are present. (#399)
- `flywheel update --apply` and an opt-in weekly check at session start that
  never installs anything. (#404)

## flywheel code

- `web_search` through SearXNG, Brave, or DuckDuckGo with no key, under the
  same permission as `web_fetch`. (#400)
- `tasks` runs up to four read-only subagents at the same time; agents that
  can write still run one at a time. (#401)
- Plugin marketplaces in Claude Code's `marketplace.json` shape:
  `flywheel plugin marketplace add`, `search`, `install NAME@MARKETPLACE`. (#402)
- Background jobs stream their output and stop at once on Linux and macOS
  too. (#403)
- Hook events PermissionRequest, PreCompact, PostCompact, SubagentStart and
  SubagentStop, for eleven in all. (#405)
- Project memory: a `remember` tool, notes kept per folder outside the tree
  and read at the next session start, `/memory` and `/forget`. (#406)

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.7.0, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- Session features are tested with a scripted model through the real agent
  loop. No hosted model was called in this release's checks, and the cloud
  backends and search providers were checked against recorded response shapes,
  not the live services. A live comparison against another harness is
  designed and waiting on a spend decision.
- The desktop app ships for Windows only; macOS and Linux desktop builds are
  not in this release.
- No Homebrew or WinGet package yet.

# Discord Gather Integration

Date: 2026-07-09

Status: channel and guild connectors implemented; live capture pending local bot credential

## Mechanism

`gather` now has dedicated Discord source adapters:

- `discord`: captures a known channel/thread id through Discord's official REST messages endpoint.
- `discord_guild`: discovers accessible guild text/news channels plus active threads, then captures each through the same message receipt path.

Both use `GATHER_DISCORD_BOT_TOKEN`; neither uses a personal user token, browser-session scraping, selfbot access, or desktop UI scraping.

Each Discord message becomes a receipted `Item`:

- `source`: `discord`
- `kind`: `message`
- `method`: `discord-api-message`
- `ref`: `channel:<id>`
- `text`: readable message fields plus canonical `raw_json`

## Files

- `C:\dev\public\gather\src\gather\discord.py`
- `C:\dev\public\gather\src\gather\run_config.py`
- `C:\dev\public\gather\src\gather\method.py`
- `C:\dev\public\gather\tests\test_discord.py`
- `C:\dev\public\gather\README.md`
- `C:\dev\local-model\configs\gather-discord-redteam-context-2026-07-09.json`
- `C:\dev\local-model\configs\gather-discord-redteam-guild-context-2026-07-09.json`

## Validation

```powershell
python -m py_compile src/gather/discord.py src/gather/run_config.py src/gather/method.py
python -m pytest tests/test_discord.py tests/test_api.py -q
python -m gather run C:/dev/local-model/configs/gather-discord-redteam-context-2026-07-09.json --json
python -m gather run C:/dev/local-model/configs/gather-discord-redteam-guild-context-2026-07-09.json --json
```

Observed:

- `15 passed`
- channel config command-level capture check failed closed with `missing required credential in environment: GATHER_DISCORD_BOT_TOKEN`
- guild config command-level capture check failed closed with `missing required credential in environment: GATHER_DISCORD_BOT_TOKEN`

## Credential check

Current environment:

- `GATHER_DISCORD_BOT_TOKEN`: absent
- `DISCORD_TOKEN`: absent

No live Discord capture was run in this session because no bot credential was available to `gather`.

## Capture command

After loading a bot token into the local environment:

```powershell
$env:GATHER_DISCORD_BOT_TOKEN = "<bot token from local secret store>"
cd C:\dev\public\gather
python -m gather run C:\dev\local-model\configs\gather-discord-redteam-context-2026-07-09.json --json
```

The configured corpus target is:

- `C:\tmp\gather_discord_redteam_context_corpus`
- `C:\tmp\gather_discord_redteam_guild_context_corpus`

## Discord targets

The channel capture config treats these as channel/thread ids; the guild capture config treats the same ids as guild/server ids:

- `1346756824233148527`
- `1105891499641684019`
- `1081121447960915989`
- `1072196207201501266`
- `1514609250222080072`

If the supplied ids are channel/thread ids, use `gather-discord-redteam-context-2026-07-09.json`. If they are server/guild ids, use `gather-discord-redteam-guild-context-2026-07-09.json`.

## Next promotion step

Add fuller guild inventory and forum-channel discovery:

- list guild channels for an authorized guild id (implemented for text/news channels)
- expand active threads into channel-like message targets (implemented)
- add archived thread search where permitted
- add forum post discovery where permitted
- emit source-federation plans before capture
- record rate-limit and permission failures as typed receipts

Then feed the captured corpus into the adversarial benchmark synthesis path as source-mined red-team context.

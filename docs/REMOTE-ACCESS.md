# Remote access: using Flywheel from your phone

Flywheel ships with **relay**, a remote MCP server that lets Claude on your
phone drive the same agent loop running on your PC. The setup is one-time.

## What you get

Your phone's Claude app connects to relay over HTTPS. Relay runs the local
coding agent on your PC, applies the same tool gates, and writes the same
hash-chained session ledger. Long tasks run in the background so a flaky
mobile connection does not kill them.

## Prerequisites

- Python 3.11+ on the PC (the Flywheel installer bundles the engine, but
  relay's remote MCP server runs from Python directly).
- A Claude plan that supports custom connectors (Free allows one).
- A Cloudflare account with one domain (free tier works). This is the
  recommended path. A direct port-forward alternative exists but requires a
  public IPv4 and your own TLS certificate.

## Quick start (Cloudflare Tunnel)

### 1. Install cloudflared

Download from
[cloudflare.com/cloudflare-one/connections/connect-networks/downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

### 2. Create a named tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create relay
cloudflared tunnel route dns relay relay.yourdomain.com
```

### 3. Configure relay

Copy `relay/.env.example` to `relay/.env`. Fill every value. Generate
secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set these for the tunnel path:

```
RELAY_REMOTE_HOST=127.0.0.1
RELAY_PUBLIC_URL=https://relay.yourdomain.com
# Leave RELAY_TLS_CERT and RELAY_TLS_KEY empty (the tunnel handles TLS)
```

### 4. Start relay

From the Flywheel repo root:

```bash
flywheel remote
```

Or with the launcher script that starts both relay and the tunnel:

```powershell
powershell -ExecutionPolicy Bypass -File relay\scripts\serve_cloudflared.ps1 -Tunnel relay
```

### 5. Verify from mobile data

Turn off wifi on your phone and run from a second terminal:

```bash
python relay/scripts/check_remote.py https://relay.yourdomain.com
```

All checks must pass before adding the connector.

### 6. Add the connector in Claude

Open **claude.ai** (web) or **Claude Desktop**. You cannot add connectors
from the phone app.

1. Settings, Connectors, Add custom connector.
2. Name: `relay`. URL: `https://relay.yourdomain.com/mcp`.
3. Advanced settings: Client ID = your `RELAY_OAUTH_CLIENT_ID`, Client
   Secret = your `RELAY_OAUTH_CLIENT_SECRET`. Add.
4. Complete the OAuth consent: enter any username and your
   `RELAY_AUTHORIZE_PASSWORD`.

### 7. Use it on the phone

Open the Claude app. In a chat, tap **+ then Connectors** and toggle
**relay** on. Ask Claude to use the relay tools (`local_agent_run`,
`local_agent_chat`, `relay.status`).

## Values that must match

| Claude connector dialog | `.env` on the PC               |
|-------------------------|---------------------------------|
| URL                     | `RELAY_PUBLIC_URL` + `/mcp`     |
| Client ID               | `RELAY_OAUTH_CLIENT_ID`         |
| Client Secret           | `RELAY_OAUTH_CLIENT_SECRET`     |
| consent password        | `RELAY_AUTHORIZE_PASSWORD`      |

`RELAY_OAUTH_REDIRECT_URIS` must include
`https://claude.ai/api/mcp/auth_callback` and
`https://claude.com/api/mcp/auth_callback`. The `.env.example` default
lists both.

## Alternative: direct port-forward (no Cloudflare)

This path requires a public IPv4 (not CGNAT) and your own certificate.

1. Set a static LAN IP for the PC (DHCP reservation on the router).
2. Create a DDNS name (DuckDNS, No-IP, or Cloudflare).
3. Port-forward external TCP 443 to your PC's LAN IP + relay port.
4. Get a TLS cert via win-acme (HTTP-01 or DNS-01 challenge).
5. Set `RELAY_REMOTE_HOST=0.0.0.0`, point `RELAY_TLS_CERT` and
   `RELAY_TLS_KEY` at the PEM files, and set `RELAY_PUBLIC_URL` to your
   DDNS name.
6. Start with `flywheel remote` or `relay\scripts\serve_remote.ps1`.

## Limitations

- Connector setup happens on the web or desktop, not the phone app.
- Sessions refresh automatically (OAuth refresh tokens, 30-day, rotated on
  use), so a phone session survives past the 1-hour access-token lifetime.
- Remote exec is off by default. Set `RELAY_ALLOW_REMOTE_EXEC=true` in
  `.env` only if you want the phone to run shell commands on your PC.
- For long tasks, use `local_agent_start` (returns a run_id immediately)
  then poll `local_agent_status` / `local_agent_result`, rather than a
  blocking `local_agent_run` that a mobile network may drop.

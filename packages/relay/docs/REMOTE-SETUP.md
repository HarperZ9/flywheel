# Driving relay from your phone and PC

relay's agent can run on your PC and be driven remotely — from **Flywheel on your
PC** and from the **Claude app on your phone** — the way Codex and Claude Code
connect to their phone apps. This guide sets both up.

The code is done: `relay.remote_mcp` serves the agent over Streamable-HTTP MCP
(`/mcp`) with OAuth 2.1. What's left is exposing it — easiest through a **Cloudflare
Tunnel** (no public IP, no port-forward, no cert) — and a few values.

---

## PC (Flywheel) — already works, no setup

The relay agent on PC is Flywheel's **Chat → Agent mode**:

1. Confirm relay is installed: `python -c "import relay; print(relay.__file__)"`.
2. Open the Flywheel desktop app (its local gateway starts with it).
3. Open **Chat**, turn **Agent mode ON**, pick a workspace root and a model
   endpoint, and run. That is the same gated, witnessed tool loop relay packages
   (writes/execs are one-use grants, every run keeps its receipt).

Optional: on the **Lanes** view, find `relay` and click **Probe now** to confirm
`relay.status` / `relay.doctor` answer (the lane is live). The desktop talks to
relay through its local gateway. The `/mcp` endpoint is for your **phone**.

---

## Mobile (Claude app) — one-time setup

### Check the blockers first

- **Plan:** any Claude plan works (Free allows one custom connector). Add the
  connector once on **claude.ai (web) or Claude Desktop**; it then appears in the
  phone app.
- **CGNAT / port-forward / cert:** all of this disappears on the **recommended
  Cloudflare Tunnel path below** — the tunnel is outbound-only, so no public IP,
  no port-forward, and no CGNAT check are needed, and Cloudflare provides the
  public cert. These only matter for the **direct port-forward** alternative: that
  path needs a public IPv4 (compare your router WAN IP against
  `curl https://api.ipify.org`; inside `100.64.0.0/10` means CGNAT, and no
  port-forward can work) and a publicly-valid CA cert (Let's Encrypt; self-signed
  is rejected).

### Recommended: Cloudflare Tunnel (no CGNAT, no port-forward, no cert)

Cloudflare's agentic networking gives relay a public HTTPS hostname through an
**outbound-only** tunnel. Your PC dials out to Cloudflare, Cloudflare serves the
certificate, and your router keeps its current settings. This is the easiest path.

1. Install **cloudflared** and a Cloudflare account (a free plan with one domain on
   Cloudflare is enough): the
   [cloudflared downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Create a **named** tunnel (a stable hostname — a registered connector needs one):
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create relay
   cloudflared tunnel route dns relay relay.yourdomain.com
   ```
3. In `.env` set the tunnel posture: `RELAY_REMOTE_HOST=127.0.0.1`, leave
   `RELAY_TLS_CERT` / `RELAY_TLS_KEY` **empty**, and set
   `RELAY_PUBLIC_URL=https://relay.yourdomain.com`. Fill the OAuth values as below.
4. Run it: `powershell -ExecutionPolicy Bypass -File scripts\serve_cloudflared.ps1 -Tunnel relay`.
   (Omit `-Tunnel relay` for a throwaway `*.trycloudflare.com` quick tunnel — good
   for a one-off reachability test, but the URL changes each run, so not for a saved
   connector.)
5. **Do not** put a Cloudflare Access policy in front of this hostname — relay runs
   its own OAuth, and an Access login page would block the connector's server-side
   OAuth. The tunnel alone is what you want.

Then skip to **[2. Configure and run relay](#2-configure-and-run-relay-the-code)**
for the OAuth values, and use `https://relay.yourdomain.com/mcp` as the connector
URL. Verify from mobile data with `python scripts/check_remote.py https://relay.yourdomain.com`.

### Alternative: a public name and cert on your own network

This path replaces the Cloudflare Tunnel above. It needs a public IPv4 address
outside `100.64.0.0/10` and a certificate you issue yourself.

- **Static LAN IP** for the PC (DHCP reservation on the router).
- **DDNS name:** create one at DuckDNS / No-IP / Cloudflare and install its
  updater on a Windows Scheduled Task so it self-heals on IP changes.
- **Port-forward** external TCP **443** → the PC's LAN IP + `RELAY_REMOTE_PORT`
  (and **80** during cert issuance if using HTTP-01). Open the port in Windows
  Firewall.
- **TLS cert** with [win-acme](https://www.win-acme.com) (run elevated):
  - HTTP-01 (needs port 80): `wacs.exe --target manual --host <ddns-name> --validation selfhosting --store pemfiles --pemfilespath C:\certs`
  - DNS-01 (Cloudflare domain, port 80 stays closed): `wacs.exe --target manual --host <name> --validation cloudflare --cloudflareapitoken <token> --store pemfiles --pemfilespath C:\certs`
  - Point `RELAY_TLS_CERT` / `RELAY_TLS_KEY` at the actual PEM filenames win-acme
    writes to `C:\certs`. win-acme installs its own 90-day renewal task; the
    launcher below restarts relay so the renewed cert is picked up.

### 2. Configure and run relay (the code)

1. Copy `.env.example` to `.env` and fill every value (generate secrets with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`). `RELAY_PUBLIC_URL`
   is your `https://` origin (the tunnel hostname, or your DDNS name). Host and TLS
   depend on your path: **tunnel** → `RELAY_REMOTE_HOST=127.0.0.1`, TLS empty;
   **direct** → `RELAY_REMOTE_HOST=0.0.0.0`, TLS filled.
2. Start it: **tunnel** →
   `powershell -ExecutionPolicy Bypass -File scripts\serve_cloudflared.ps1 -Tunnel relay`;
   **direct** → `powershell -ExecutionPolicy Bypass -File scripts\serve_remote.ps1`.
3. **From mobile data**, with home wifi switched off, check that it is reachable:
   `python scripts/check_remote.py https://<your-host>`. Move on to the connector
   dialog once it prints PASS (valid cert, metadata, `/mcp` answering).

### 3. Add the connector (on claude.ai web or Claude Desktop)

1. **Settings → Connectors → Add custom connector.**
2. **Name:** `relay`. **URL:** `https://<ddns-name>/mcp`, the MCP endpoint itself
   and the final URL after any redirect.
3. **Advanced settings:** **Client ID** = your `RELAY_OAUTH_CLIENT_ID`,
   **Client Secret** = your `RELAY_OAUTH_CLIENT_SECRET`. Add.
4. Complete the OAuth consent: a browser prompt (HTTP Basic) appears — enter **any
   username** and your **`RELAY_AUTHORIZE_PASSWORD`**. Claude redirects back and
   the connector shows connected.

### 4. Use it on the phone

Open the Claude app → in a chat tap **+ → Connectors → toggle `relay` on**. Ask
Claude to use the relay tools (`local_agent_run`, `local_agent_chat`,
`relay.status`, …). Writes and remote exec start **off**:

| To let the phone | Set in the server's environment | And the call sends |
|---|---|---|
| write files | `RELAY_ALLOW_WRITE=1` | `allow_write: true` |
| run shell commands | `RELAY_ALLOW_EXEC=1` and `RELAY_ALLOW_REMOTE_EXEC=1` | |

The launch sets the ceiling: a call asks within the grants the server started with. Runs stay inside
`RELAY_MCP_ROOT`, which defaults to the directory the server starts in (the repo
root, for the launch scripts).

Set these grant lines in the shell that runs the script. relay reads them from
the process environment and skips them in `.env`, because a run allowed to write
could edit `.env` and grant itself exec at the next automatic restart. For
example:

```powershell
$env:RELAY_ALLOW_WRITE = "1"; $env:RELAY_MCP_ROOT = "C:\work\project"
powershell -ExecutionPolicy Bypass -File scripts\serve_remote.ps1
```

The server lists any grant line it finds in `.env` at startup and in
`relay.doctor` (`env_file_ignored`). Point `RELAY_MCP_ROOT` at the workspace the
phone should edit. relay's own checkout is a poor root, because a file written
there can later run as relay's code. The shell starts in the run's root and can
reach every path your account can, so turn on remote exec for a session you mean
to give that reach.

---

## Values that must match

| Claude connector dialog | your `.env` on the PC |
|---|---|
| URL | `RELAY_PUBLIC_URL` + `/mcp` |
| Client ID | `RELAY_OAUTH_CLIENT_ID` |
| Client Secret | `RELAY_OAUTH_CLIENT_SECRET` |
| consent password | `RELAY_AUTHORIZE_PASSWORD` |

`RELAY_OAUTH_REDIRECT_URIS` must include `https://claude.ai/api/mcp/auth_callback`
(and `https://claude.com/api/mcp/auth_callback`) — the `.env.example` default
already lists both.

## Known limitations

- **Sessions refresh automatically** (OAuth refresh tokens, 30-day, rotated on
  use), so a phone session survives past the 1-hour access-token lifetime.
- **Cert renewal (direct path):** relay picks up a renewed cert on restart, and
  the launcher's restart loop does that for you. On the Cloudflare Tunnel path,
  Cloudflare renews its own cert.
- **CGNAT:** the direct port-forward path needs a public IPv4. If your ISP puts
  you behind carrier-grade NAT, use the **Cloudflare Tunnel** path, which dials
  out and works from any connection.
- **Background runs for a flaky link:** for a long task, prefer `local_agent_start`
  (returns a run_id at once) then poll `local_agent_status` / `local_agent_result`,
  rather than a single blocking `local_agent_run` that a mobile network may drop.
  When `RELAY_RUN_ROOT` is set, Relay checkpoints witnessed progress during the
  background run. If the server restarts before completion, the run reloads as
  `interrupted` with the partial ledger entries preserved; this does not mean the
  action completed or passed acceptance.

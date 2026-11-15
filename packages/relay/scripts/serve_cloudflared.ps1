# relay remote MCP behind a Cloudflare Tunnel (Windows).
#
# Cloudflare's agentic networking exposes relay's agent to your phone WITHOUT a
# public IP, a port-forward, DDNS, or your own TLS cert. The tunnel is outbound
# only, so CGNAT stops mattering; Cloudflare terminates public HTTPS at your
# tunnel hostname and forwards to relay on localhost.
#
# In .env, set the tunnel posture:
#   RELAY_REMOTE_HOST=127.0.0.1     # cloudflared reaches relay locally; do NOT expose the LAN
#   RELAY_TLS_CERT=                 # empty: Cloudflare provides the public cert
#   RELAY_TLS_KEY=                  # empty
#   RELAY_PUBLIC_URL=https://<your-tunnel-hostname>   # the DNS name your named tunnel routes
#
# Prereqs: a Cloudflare account and `cloudflared` installed
# (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
# Named tunnel = a STABLE hostname, required for a registered Claude connector:
#   cloudflared tunnel login
#   cloudflared tunnel create relay
#   cloudflared tunnel route dns relay <your-tunnel-hostname>
# then run:   powershell -ExecutionPolicy Bypass -File scripts\serve_cloudflared.ps1 -Tunnel relay
# Without -Tunnel this opens a THROWAWAY quick tunnel (random *.trycloudflare.com
# URL that changes every run) -- fine for a one-off test, not for a saved connector.
param([string]$Tunnel = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
    Write-Error "no .env in $root -- copy .env.example to .env and fill it in first"
    exit 1
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared not found on PATH -- install it, then re-run"
    exit 1
}

# relay's own port (cloudflared forwards to it on localhost); default 8787.
$port = 8787
foreach ($line in Get-Content ".env") {
    if ($line -match '^\s*RELAY_REMOTE_PORT\s*=\s*(\d+)') { $port = [int]$Matches[1] }
}

while ($true) {
    # relay serves plain HTTP on localhost; the tunnel carries public TLS.
    $relay = Start-Process python -ArgumentList '-m', 'relay.remote_mcp' -PassThru -NoNewWindow
    try {
        if ($Tunnel) {
            cloudflared tunnel --url "http://localhost:$port" run $Tunnel
        } else {
            Write-Host "No -Tunnel name: opening a throwaway quick tunnel (test only; the URL changes each run)."
            cloudflared tunnel --url "http://localhost:$port"
        }
    } finally {
        if ($relay -and -not $relay.HasExited) { Stop-Process -Id $relay.Id -Force }
    }
    Write-Host "tunnel or relay exited; restarting in 5s (Ctrl+C to stop)..."
    Start-Sleep -Seconds 5
}

# relay remote MCP launcher (Windows).
# Loads .env from the repo root and serves, auto-restarting on exit (so a cert
# renewal or a crash comes back up). Run from an elevated shell if binding 443:
#   powershell -ExecutionPolicy Bypass -File scripts\serve_remote.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
    Write-Error "no .env in $root — copy .env.example to .env and fill it in first"
    exit 1
}

# main() reads .env itself (RELAY_ENV_FILE, default .env) and validates the config.
while ($true) {
    python -m relay.remote_mcp
    Write-Host "relay remote MCP exited; restarting in 5s (Ctrl+C to stop)..."
    Start-Sleep -Seconds 5
}

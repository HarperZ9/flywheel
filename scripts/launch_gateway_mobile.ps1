# launch_gateway_mobile.ps1 - start the Flywheel gateway bound for the phone.
#
# Binds the gateway on loopback (so the PC desktop app keeps its 127.0.0.1 path)
# AND on this machine's Tailscale address, so the phone reaches the same engine
# over the Tailscale mesh from any network. It never binds 0.0.0.0, so no other
# LAN is exposed. The bearer token and the Host allowlist still gate every
# request. The Tailscale and LAN addresses are read live at launch; no address
# is written into this file.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\launch_gateway_mobile.ps1
#     -Lan          also bind the same-wifi LAN address, for when the phone and
#                   PC share one router and Tailscale is not in play
#     -Port 8799    override the port (default 8799)
#     -Python py    override the interpreter (default "python")
#
# Stop: Ctrl-C in this window, or close it.

[CmdletBinding()]
param(
    [int]$Port = 8799,
    [switch]$Lan,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

# Run from the repo root so gateway.py's relative paths resolve.
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Get-TailscaleIPv4 {
    # Prefer tailscale on PATH; fall back to the default install location.
    $exe = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
    if (-not $exe) {
        $candidate = "C:\Program Files\Tailscale\tailscale.exe"
        if (Test-Path $candidate) { $exe = $candidate }
    }
    if (-not $exe) { return $null }
    try { $out = & $exe ip -4 2>$null } catch { return $null }
    if (-not $out) { return $null }
    # `tailscale ip -4` prints one IPv4 per line; take the first well-formed one.
    return ($out | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1)
}

function Get-LanIPv4 {
    # The IPv4 on the adapter that owns the default route: the router-facing NIC.
    # Excludes loopback, APIPA (169.254/16), and the Tailscale CGNAT range
    # (100.64/10) so the mesh address is never mistaken for the LAN address.
    $cfg = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1
    if (-not $cfg) { return $null }
    $ip = $cfg.IPv4Address.IPAddress
    if ($ip -match '^(127\.|169\.254\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)') { return $null }
    return $ip
}

$bindHosts = @("127.0.0.1")
$allowHosts = @()

$ts = Get-TailscaleIPv4
if ($ts) {
    Write-Host "Tailscale address: $ts  (phone reaches the PC over the mesh)"
    $bindHosts += $ts
    $allowHosts += $ts
} else {
    Write-Host "Tailscale not detected. Binding loopback only unless -Lan is set."
    Write-Host "  Start Tailscale, or pass -Lan for same-wifi reach."
}

if ($Lan) {
    $lan = Get-LanIPv4
    if ($lan) {
        Write-Host "LAN address: $lan  (phone and PC on the same router)"
        $bindHosts += $lan
        $allowHosts += $lan
    } else {
        Write-Host "No LAN address with a default route found; skipping -Lan."
    }
}

# Build the argument list: loopback plus any remote binds, each also allow-listed
# so its Host header passes the DNS-rebinding check.
$gwArgs = @("harness/gateway.py", "--port", "$Port")
foreach ($h in $bindHosts)  { $gwArgs += @("--host", $h) }
foreach ($h in $allowHosts) { $gwArgs += @("--allow-host", $h) }

Write-Host ""
Write-Host "Binding: $($bindHosts -join ', ')  on port $Port"
Write-Host "Starting the gateway. Ctrl-C to stop."
Write-Host ""

& $Python @gwArgs
exit $LASTEXITCODE

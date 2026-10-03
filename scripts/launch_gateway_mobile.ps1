# launch_gateway_mobile.ps1 - start the Flywheel gateway bound for the phone.
#
# Binds the gateway on loopback (so the PC desktop app keeps its 127.0.0.1 path)
# AND, when available, on this machine's validated Tailscale address so the phone
# reaches the same engine over the tailnet. It never binds 0.0.0.0. The bearer
# token and the Host allowlist still gate every request. Tailnet planning reads
# `tailscale status --json` only; it does not login, connect, serve, funnel,
# change ACLs, or expose ports.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\launch_gateway_mobile.ps1
#     -TailnetOnly  require running/self-online Tailscale and bind only loopback
#                   plus the explicit tailnet IPv4; no LAN fallback
#     -Plan         print the redacted tailnet plan and exit without listening
#     -ReceiptPath  write the redacted plan/receipt JSON to this file
#     -Lan          also bind the same-wifi LAN address, for when the phone and
#                   PC share one router and Tailscale is not in play; rejected
#                   when combined with -TailnetOnly
#     -Port 8799    override the port (default 8799)
#     -Python py    override the interpreter (default "python")
#
# Stop: Ctrl-C in this window, or close it.

[CmdletBinding()]
param(
    [int]$Port = 8799,
    [switch]$Lan,
    [switch]$TailnetOnly,
    [switch]$Plan,
    [string]$ReceiptPath,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

# Run from the repo root so gateway.py's relative paths resolve.
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Test-GatewayTokenPresent {
    $flywheelHome = $env:FLYWHEEL_HOME
    if (-not $flywheelHome) {
        $flywheelHome = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".flywheel"
    }
    return (Test-Path (Join-Path $flywheelHome "gateway.token"))
}

function Get-TailnetGatewayPlan {
    $args = @("-m", "harness.tailscale_station", "--port", "$Port")
    if (Test-GatewayTokenPresent) { $args += "--token-present" }
    $out = & $Python @args 2>$null
    if (-not $out) {
        return [pscustomobject]@{
            schema = "flywheel.tailnet-station-plan/v1"
            transport = "tailnet"
            ok = $false
            reason = "tailnet_plan_unavailable"
            connection_url = $null
            bind_hosts = @()
            allow_hosts = @()
            token_present = (Test-GatewayTokenPresent)
        }
    }
    return ($out | ConvertFrom-Json)
}

function Write-RedactedPlan {
    param([object]$TailnetPlan)
    $json = $TailnetPlan | ConvertTo-Json -Depth 8
    if ($ReceiptPath) {
        if ([System.IO.Path]::IsPathRooted($ReceiptPath)) { $target = [System.IO.Path]::GetFullPath($ReceiptPath) }
        else { $target = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $ReceiptPath)) }
        Set-Content -LiteralPath $target -Value $json -Encoding UTF8
        Write-Host "Wrote redacted tailnet plan: $target"
    } else {
        Write-Output $json
    }
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

if ($TailnetOnly -and $Lan) {
    throw "-TailnetOnly cannot be combined with -Lan because tailnet-only mode has no LAN fallback."
}

$tailnetPlan = Get-TailnetGatewayPlan

if ($Plan) {
    Write-RedactedPlan $tailnetPlan
    if ($tailnetPlan.ok) { exit 0 }
    exit 2
}

$bindHosts = @("127.0.0.1")
$allowHosts = @()

if ($tailnetPlan.ok) {
    Write-Host "Tailscale address: $($tailnetPlan.allow_hosts[0])  (phone reaches the PC over the tailnet)"
    $bindHosts = @($tailnetPlan.bind_hosts)
    $allowHosts = @($tailnetPlan.allow_hosts)
} elseif ($TailnetOnly) {
    Write-RedactedPlan $tailnetPlan
    Write-Error "Tailnet-only gateway requested but unavailable: $($tailnetPlan.reason)"
    exit 2
} else {
    Write-Host "Tailscale unavailable ($($tailnetPlan.reason)). Binding loopback only unless -Lan is set."
    Write-Host "  Start Tailscale, or pass -Lan for same-wifi reach."
}

if (-not $TailnetOnly -and $Lan) {
    $lan = Get-LanIPv4
    if ($lan) {
        Write-Host "LAN address: $lan  (phone and PC on the same router)"
        $bindHosts += $lan
        $allowHosts += $lan
    } else {
        Write-Host "No LAN address with a default route found; skipping -Lan."
    }
}

if ($ReceiptPath) {
    $receipt = [pscustomobject]@{
        schema = "flywheel.mobile-gateway-plan/v1"
        transport = if ($tailnetPlan.ok) { "tailnet" } elseif ($Lan) { "lan_optional" } else { "loopback" }
        status = "planned"
        gateway_started = $false
        connection_url = if ($tailnetPlan.ok) { $tailnetPlan.connection_url } else { $null }
        bind_hosts = $bindHosts
        allow_hosts = $allowHosts
        token_present = (Test-GatewayTokenPresent)
    }
    Write-RedactedPlan $receipt
}

# Build the argument list: loopback plus any remote binds, each also allow-listed
# so its Host header passes the DNS-rebinding check.
$gwArgs = @("harness/gateway.py", "--port", "$Port")
if ($TailnetOnly) { $gwArgs += "--strict-bind" }
foreach ($h in $bindHosts)  { $gwArgs += @("--host", $h) }
foreach ($h in $allowHosts) { $gwArgs += @("--allow-host", $h) }

Write-Host ""
Write-Host "Binding: $($bindHosts -join ', ')  on port $Port"
Write-Host "Starting the gateway. Ctrl-C to stop."
Write-Host ""

& $Python @gwArgs
exit $LASTEXITCODE

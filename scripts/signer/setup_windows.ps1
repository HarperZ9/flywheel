# Set up the Flywheel record signer under its own Windows account.
#
# Run in an elevated PowerShell:
#   .\scripts\signer\setup_windows.ps1 -Python "C:\Program Files\Python313\python.exe"
#
# The python given must import flywheel's `harness` package, a signing
# backend and the anchor extra (pip install "flywheel-verify[signing,anchor]"),
# and the new account must be
# able to read it. A Python installed for all users works; one under a
# private profile (AppData) does not.
#
# What it creates:
#   account  flywheel-signer   a local standard user, not an administrator
#   home     C:\ProgramData\FlywheelSigner   ACL: flywheel-signer and SYSTEM only
#   pipe     \\.\pipe\flywheel-signer   created by the signer with its own DACL
#   task     FlywheelSigner   starts the signer at boot as flywheel-signer
#   anchors  C:\ProgramData\FlywheelSignerAnchors   public receipts; Users may read
#   task     FlywheelSignerAnchor   every 15 minutes (-AnchorEveryMinutes), logs each
#            moved head in Sigstore Rekor and OpenTimestamps; -NoAnchor skips it
#
# The account password is random, used once to register the task, and never
# shown or stored by this script. Nothing here copies or prints the seed.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$Account = "flywheel-signer",
    [string]$HomeDir = "C:\ProgramData\FlywheelSigner",
    [string]$Pipe = "\\.\pipe\flywheel-signer",
    [string]$AnchorDir = "C:\ProgramData\FlywheelSignerAnchors",
    [int]$AnchorEveryMinutes = 15,
    [switch]$NoAnchor
)
$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run elevated: creating the account and its ACL needs an administrator."
}
& $Python -c "import harness.signer.keys"
if ($LASTEXITCODE -ne 0) { throw "$Python cannot import harness.signer; install flywheel first." }
if (-not $NoAnchor) {
    & $Python -c "import nacl.bindings"
    if ($LASTEXITCODE -ne 0) {
        throw "Public anchoring needs pynacl: pip install `"flywheel-verify[signing,anchor]`" (or pass -NoAnchor)."
    }
}

$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
# Base64 of 24 random bytes, plus one character of each class for the
# local password policy.
$plain = [Convert]::ToBase64String($bytes) + "aA1!"
$secure = ConvertTo-SecureString $plain -AsPlainText -Force
if (-not (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue)) {
    New-LocalUser -Name $Account -Password $secure -PasswordNeverExpires `
        -UserMayNotChangePassword -Description "Flywheel record signer" | Out-Null
} else {
    Set-LocalUser -Name $Account -Password $secure
}

New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null
# Only the signer account and SYSTEM. Administrators are left off on purpose:
# an administrator can still take ownership, which SEPARATE-SIGNER.md states.
icacls $HomeDir /inheritance:r /grant:r "${Account}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null

$cmdArgs = "-m harness.signer init --home `"$HomeDir`" && `"$Python`" -m harness.signer " +
        "serve --home `"$HomeDir`" --address $Pipe"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"`"$Python`" $cmdArgs`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "FlywheelSigner" -Action $action -Trigger $trigger `
    -Settings $settings -User $Account -Password $plain -RunLevel Limited -Force | Out-Null
if (-not $NoAnchor) {
    New-Item -ItemType Directory -Force -Path $AnchorDir | Out-Null
    # Receipts hold hashes and public log entries only. The signer writes them;
    # everyone else may read them, so any user can verify a store against them.
    icacls $AnchorDir /inheritance:r /grant:r "${Account}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" `
        "*S-1-5-32-545:(OI)(CI)RX" | Out-Null
    $anchorArgs = "-m harness.signer anchor --home `"$HomeDir`" --out `"$AnchorDir`""
    $anchorAction = New-ScheduledTaskAction -Execute $Python -Argument $anchorArgs
    $anchorTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
        -RepetitionInterval (New-TimeSpan -Minutes $AnchorEveryMinutes)
    Register-ScheduledTask -TaskName "FlywheelSignerAnchor" -Action $anchorAction `
        -Trigger $anchorTrigger -User $Account -Password $plain -RunLevel Limited -Force | Out-Null
}
$plain = $null
Start-ScheduledTask -TaskName "FlywheelSigner"

$hello = $null
foreach ($i in 1..50) {
    $hello = & $Python -m harness.signer hello --address $Pipe 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Milliseconds 200
}
if (-not $hello) { throw "The signer did not answer on $Pipe. Check the FlywheelSigner task." }
$info = $hello | ConvertFrom-Json

Write-Output "flywheel-signer is running as $Account."
Write-Output "Isolation it measured for this shell: $($info.isolation.mode)"
Write-Output ""
Write-Output "Give the agent's hook these variables, and set them where you verify:"
Write-Output "  FLYWHEEL_SIGNER=$Pipe"
Write-Output "  FLYWHEEL_SIGNER_PUBKEY=$($info.public_key)"
if ($NoAnchor) { Write-Output "  (public anchoring is off: -NoAnchor)" }
else { Write-Output "  FLYWHEEL_SIGNER_ANCHORS=$AnchorDir" }
Write-Output ""
Write-Output "Pin the same key when you verify:"
Write-Output "  flywheel monitor verify <home> --trust-root $($info.public_key)"
Write-Output ""
Write-Output "Do not run the agent elevated: an administrator can take ownership of $HomeDir."

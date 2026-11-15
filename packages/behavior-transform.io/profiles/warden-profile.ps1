# warden-profile.ps1 - IO Channel shell integration for PowerShell
#
# Sources the safe_* channel passthrough for WARDEN CLI, Claude Code, Codex.
# Architecture: [A -> io_channel.py -> CLI/Harness -> io_channel.py -> B]
#
# To activate in your PowerShell profile, add:
#   . "$env:USERPROFILE\AGENTS\warden_shell\tools\warden-profile.ps1"
#
# To activate in Windows Terminal for all PS sessions, add the above line
# to: $PROFILE (run notepad $PROFILE to edit)

$WARDEN_TOOLS = (Resolve-Path (Join-Path $PSScriptRoot "..\tools")).Path
$IO_CHANNEL   = "$WARDEN_TOOLS\io_channel.py"
$IO_MODE      = "$WARDEN_TOOLS\io_mode.py"
if (-not $env:WARDEN_IO_CHANNEL) {
    $env:WARDEN_IO_CHANNEL = (python $IO_MODE status --mode-only).Trim()
}

# --- Session IO mode ---------------------------------------------------------

function IO-On {
    $mode = (python $IO_MODE on --mode-only).Trim()
    $env:WARDEN_IO_CHANNEL = $mode
    $env:WARDEN_IO = $mode
    Write-Host "WARDEN IO Channel: on" -ForegroundColor DarkGray
}

function IO-Off {
    $mode = (python $IO_MODE off --mode-only).Trim()
    $env:WARDEN_IO_CHANNEL = $mode
    $env:WARDEN_IO = $mode
    Write-Host "WARDEN IO Channel: off" -ForegroundColor DarkGray
}

function IO-Status {
    $mode = (python $IO_MODE status --mode-only).Trim()
    Write-Host "WARDEN IO Channel: $mode" -ForegroundColor DarkGray
}

# --- Core wrapper ------------------------------------------------------------

function Invoke-IOChannel {
    <#
    .SYNOPSIS
        Passthrough container: routes a CLI invocation through io_channel.py.
    .DESCRIPTION
        Stdin bytes are calibrated via safe_input before reaching the CLI.
        Stdout/stderr are calibrated via safe_exec before returning to operator.
        Pass channel flags (--include-stderr, --report, --no-calibrate, etc.)
        before --, then the CLI command and its args after --.
    .EXAMPLE
        Invoke-IOChannel -- claude --print "task"
        Invoke-IOChannel --report -- warden scan --dir .
    #>
    param(
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$PassArgs
    )
    python $IO_CHANNEL @PassArgs
    return $LASTEXITCODE
}

# --- CLI wrappers ------------------------------------------------------------

function Use-WARDEN  { Invoke-IOChannel -- warden  @args }
function Use-Claude  { Invoke-IOChannel -- claude  @args }
function Use-Codex   { Invoke-IOChannel -- codex   @args }

# --- Direct safe_* shortcuts -------------------------------------------------

function Safe-Read  { param([string]$Path) python "$WARDEN_TOOLS\safe_read.py"  $Path @args }
function Safe-Write { param([string]$Dest) python "$WARDEN_TOOLS\safe_write.py" $Dest @args }
function Safe-Exec  { python "$WARDEN_TOOLS\safe_exec.py"  -- @args }
function Safe-Fetch { python "$WARDEN_TOOLS\safe_fetch.py" @args }
function Safe-Input { python "$WARDEN_TOOLS\safe_input.py" @args }

# --- Aliases (only created if the native executable exists) ------------------

if (Get-Command warden -CommandType Application -ErrorAction SilentlyContinue) {
    Set-Alias -Name warden -Value Use-WARDEN -Scope Global -Option AllScope -Force
}
if (Get-Command claude -CommandType Application -ErrorAction SilentlyContinue) {
    Set-Alias -Name claude -Value Use-Claude -Scope Global -Option AllScope -Force
}
if (Get-Command codex -CommandType Application -ErrorAction SilentlyContinue) {
    Set-Alias -Name codex  -Value Use-Codex  -Scope Global -Option AllScope -Force
}

Write-Host "WARDEN IO Channel loaded ($env:WARDEN_IO_CHANNEL)." -ForegroundColor DarkGray

# --- Container ecosystem entry point -----------------------------------------

function Invoke-Container {
    <#
    .SYNOPSIS
        Container ecosystem orchestrator. Subcommands: status, init, calibrate, wrap, routes.
    .EXAMPLE
        container status
        container init
        container wrap -- claude --print "task"
    #>
    param([Parameter(ValueFromRemainingArguments)][string[]]$PassArgs)
    python "$WARDEN_TOOLS\container_ecosystem.py" @PassArgs
    return $LASTEXITCODE
}
Set-Alias -Name container -Value Invoke-Container -Scope Global -Option AllScope -Force

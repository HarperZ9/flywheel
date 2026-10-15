# Install the flywheel command for this user on Windows.
#
#   irm https://raw.githubusercontent.com/HarperZ9/flywheel/main/install.ps1 | iex
#
# Makes a private virtual environment under %LOCALAPPDATA%\Flywheel\cli,
# installs flywheel-verify from PyPI into it, and adds its Scripts folder to the
# user PATH (pass -NoPath, or set FLYWHEEL_NO_PATH=1, to skip that). Needs Python
# 3.11 or newer. The Windows app installer is separate and needs no Python.
# Settings: FLYWHEEL_VERSION, FLYWHEEL_SOURCE, FLYWHEEL_INSTALL_DIR.
# To remove: delete the install folder and its Scripts entry from the user PATH.
param([switch]$NoPath)
$ErrorActionPreference = "Stop"

$dest = if ($env:FLYWHEEL_INSTALL_DIR) { $env:FLYWHEEL_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Flywheel\cli" }
$py = $null
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = Get-Command $candidate[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $args0 = @($candidate | Select-Object -Skip 1)
    & $exe.Source @args0 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = @($exe.Source) + $args0; break }
}
if (-not $py) { Write-Error "flywheel needs Python 3.11 or newer; install it and run this again."; exit 1 }

$req = if ($env:FLYWHEEL_SOURCE) { $env:FLYWHEEL_SOURCE } elseif ($env:FLYWHEEL_VERSION) { "flywheel-verify==$($env:FLYWHEEL_VERSION)" } else { "flywheel-verify" }
Write-Host "Installing $req into $dest"
& $py[0] @($py | Select-Object -Skip 1) -m venv $dest
if ($LASTEXITCODE -ne 0) { throw "could not create the virtual environment" }
$venvPy = Join-Path $dest "Scripts\python.exe"
& $venvPy -m pip install --quiet --disable-pip-version-check --upgrade $req
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
$scripts = Join-Path $dest "Scripts"
& (Join-Path $scripts "flywheel.exe") --version

if (-not $NoPath -and $env:FLYWHEEL_NO_PATH -ne "1") {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not ($userPath -split ";" | Where-Object { $_ -eq $scripts })) {
        [Environment]::SetEnvironmentVariable("Path", (($userPath, $scripts) -ne "" -join ";"), "User")
        Write-Host "Added $scripts to your user PATH; open a new terminal to use it."
    }
}
Write-Host "Next: flywheel doctor, then flywheel code in a project folder."

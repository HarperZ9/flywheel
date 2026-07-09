# launch_32b_training.ps1 - start the RAM-gated, resumable 32B QLoRA CPT run.
#
# Run this when the machine is close to idle. This box has 32 GB RAM; loading
# the 82 GB 32B and quantizing to 4-bit streams ~20 GB through RAM, so the run
# only completes cleanly when ~22 GB RAM is free. The supervisor waits for that
# on its own, so you can start it and walk away. Closing Chrome, Discord, game
# launchers, and other heavy apps first makes the wait short.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\launch_32b_training.ps1
# Monitor: Get-Content E:\local-model-run\logs\phase2-32b-supervisor.log -Tail 5 -Wait
# Stop:    New-Item E:\local-model-run\STOP_32B -ItemType File -Force

$ErrorActionPreference = "Stop"

$stop = "E:\local-model-run\STOP_32B"
if (Test-Path $stop) {
    Remove-Item $stop -Force
    Write-Host "Removed STOP flag."
}

$free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
Write-Host "Free RAM now: $free GB. The supervisor needs ~22 GB free before it loads."
if ($free -lt 20) {
    Write-Host "Tip: close heavy apps (Chrome, Discord, launchers) to shorten the wait."
}

# Launch the supervisor inside a detached WSL screen session named train32b.
wsl.exe -e bash -lc "screen -dmS train32b bash /mnt/c/dev/local-model/scripts/run_phase2_32b_supervised.sh"
Start-Sleep -Seconds 3
wsl.exe -e bash -lc "screen -ls" 2>$null

Write-Host ""
Write-Host "Started. The supervisor is waiting for RAM, then it will train ~18h,"
Write-Host "checkpointing every 50 steps to E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-32b."
Write-Host "Watch it with:  Get-Content E:\local-model-run\logs\phase2-32b-supervisor.log -Tail 5 -Wait"

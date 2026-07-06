@echo off
REM wsl_vllm_run.cmd - Windows launcher for the vLLM/WSL2 spike (Phase C).
REM PREREQ: WSL2 installed (run, elevated:  wsl --install  ; reboot only if it asks)
REM         and the default distro (Ubuntu) launched once to set a UNIX user/pass.
REM Runs wsl_vllm_spike.sh inside the default WSL2 distro.
echo === launching vLLM/WSL2 spike in default WSL2 distro ===
wsl bash /mnt/c/dev/local-model/harness/wsl_vllm_spike.sh
echo === spike script returned rc=%ERRORLEVEL% ===

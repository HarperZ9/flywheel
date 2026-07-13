@echo off
REM Launcher for Phase 2 QLoRA continued-pretraining (Windows equivalent of run_phase2.sh).
REM Pass --smoke for the 2-step VRAM-envelope test first. Everything logs to E:.
setlocal
set RUN=E:\local-model-run
set PY=%RUN%\venv\Scripts\python.exe
set HF_HOME=%RUN%\hf-cache
set PIP_CACHE_DIR=%RUN%\pip-cache
set TMP=%RUN%\tmp
set TEMP=%RUN%\tmp
set PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
set BITSANDBYTES_NOWELCOME=1
if not exist "%RUN%\tmp" mkdir "%RUN%\tmp"
if not exist "%RUN%\logs" mkdir "%RUN%\logs"
set TAG=full
for %%A in (%*) do if "%%A"=="--smoke" set TAG=smoke
set LOG=%RUN%\logs\phase2-%TAG%.log
set ERR=%RUN%\logs\phase2-%TAG%.err
echo === %DATE% %TIME% phase2 (%TAG%) START ===>> "%LOG%" 2>>"%ERR%"
"%PY%" -u "C:\dev\local-model\train\qlora_cpt.py" %* 1>>"%LOG%" 2>>"%ERR%"
echo === %DATE% %TIME% phase2 (%TAG%) DONE rc=%ERRORLEVEL% ===>> "%LOG%" 2>>"%ERR%"
endlocal

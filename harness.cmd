@echo off
setlocal
set "HARNESS_ROOT=%~dp0"
python "%HARNESS_ROOT%scripts\run_harness_cli.py" %*
exit /b %ERRORLEVEL%

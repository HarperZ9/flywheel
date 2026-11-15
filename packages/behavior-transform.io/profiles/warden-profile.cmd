@echo off
:: warden-profile.cmd - IO Channel shell integration for Windows CMD
::
:: Architecture: [A -> io_channel.py -> CMD shell -> io_channel.py -> B]
::
:: To activate automatically for all CMD sessions (one-time, per-user):
::   reg add "HKCU\Software\Microsoft\Command Processor" /v AutoRun /t REG_SZ /d "\"%USERPROFILE%\AGENTS\warden_shell\tools\warden-profile.cmd\"" /f
::
:: Or call manually at the start of a CMD session:
::   call %USERPROFILE%\AGENTS\warden_shell\tools\warden-profile.cmd

set WARDEN_TOOLS=%~dp0..\tools
set IO_CHANNEL=%WARDEN_TOOLS%\io_channel.py
set IO_MODE=%WARDEN_TOOLS%\io_mode.py
if "%WARDEN_IO_CHANNEL%"=="" for /f %%i in ('python "%IO_MODE%" status --mode-only') do set WARDEN_IO_CHANNEL=%%i

:: Session IO mode
doskey io-on=python "%IO_MODE%" on$Tset WARDEN_IO_CHANNEL=on$Tset WARDEN_IO=on$Techo WARDEN IO Channel: on
doskey io-off=python "%IO_MODE%" off$Tset WARDEN_IO_CHANNEL=off$Tset WARDEN_IO=off$Techo WARDEN IO Channel: off
doskey io-status=python "%IO_MODE%" status

:: CLI wrappers via doskey (active for this CMD session)
doskey warden=python "%IO_CHANNEL%" -- warden $*
doskey claude=python "%IO_CHANNEL%" -- claude $*
doskey codex=python "%IO_CHANNEL%" -- codex $*

:: Direct safe_* shortcuts
doskey safe-read=python "%WARDEN_TOOLS%\safe_read.py" $*
doskey safe-write=python "%WARDEN_TOOLS%\safe_write.py" $*
doskey safe-exec=python "%WARDEN_TOOLS%\safe_exec.py" -- $*
doskey safe-fetch=python "%WARDEN_TOOLS%\safe_fetch.py" $*
doskey safe-input=python "%WARDEN_TOOLS%\safe_input.py" $*

echo WARDEN IO Channel loaded. (CMD, %WARDEN_IO_CHANNEL%)

:: --- Container ecosystem entry point ----------------------------------------
doskey container=python "%WARDEN_TOOLS%\container_ecosystem.py" $*


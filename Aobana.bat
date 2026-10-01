@echo off
set "AOBANA_ROOT=%~dp0"
if not exist "%AOBANA_ROOT%aobana\__main__.py" set "AOBANA_ROOT=%~dp0..\"
cd /d "%AOBANA_ROOT%"
if exist "%AOBANA_ROOT%python\python.exe" (
    "%AOBANA_ROOT%python\python.exe" -m aobana
) else (
    python -m aobana
)

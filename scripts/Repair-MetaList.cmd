@echo off
setlocal
set "METALIST_REPAIR_DIRECTORY=%~dp0"
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference = 'Stop'; $toolDirectory = & uv tool dir; if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the existing MetaList installation.' }; $repairPython = Join-Path -Path ($toolDirectory.Trim()) -ChildPath 'metalist\Scripts\python.exe'; if (-not (Test-Path -LiteralPath $repairPython)) { throw 'MetaList Python was not found in the uv tool directory.' }; & $repairPython -I (Join-Path $env:METALIST_REPAIR_DIRECTORY 'update_installer.py'); exit $LASTEXITCODE"
set "metalist_repair_exit=%ERRORLEVEL%"
pause
exit /b %metalist_repair_exit%

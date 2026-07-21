@echo off
setlocal
set "MODULE_DIR=%~dp0.."
for %%I in ("%MODULE_DIR%\..\..") do set "REPO_ROOT=%%~fI"

pushd "%REPO_ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_hanzi_writer_data.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

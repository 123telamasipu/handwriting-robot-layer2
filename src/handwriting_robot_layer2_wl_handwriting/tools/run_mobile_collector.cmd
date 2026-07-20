@echo off
setlocal
set "MODULE_DIR=%~dp0.."
for %%I in ("%MODULE_DIR%\..\..") do set "REPO_ROOT=%%~fI"
set "VENV_PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"

pushd "%REPO_ROOT%"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -m src.handwriting_robot_layer2_wl_handwriting.mobile_server %*
) else (
    py -3 -m src.handwriting_robot_layer2_wl_handwriting.mobile_server %*
)
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
popd
exit /b %EXIT_CODE%

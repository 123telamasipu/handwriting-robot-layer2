@echo off
setlocal
set "MODULE_DIR=%~dp0.."
for %%I in ("%MODULE_DIR%\..\..") do set "REPO_ROOT=%%~fI"
set "VENV_PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"

pushd "%REPO_ROOT%"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -m src.handwriting_robot_layer2_wl_handwriting.style_generator_cli %*
) else (
    py -3 -m src.handwriting_robot_layer2_wl_handwriting.style_generator_cli %*
)
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
py -3 -m src.handwriting_robot_layer2_wl_handwriting.similarity_cli %*

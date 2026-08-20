@echo off
REM Double-click this file to launch the no-stress MA concentration calculator.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.10+ from https://python.org
    echo and make sure "Add python.exe to PATH" is checked during setup.
    pause
    exit /b 1
)

python -c "import pandas, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo Installing required packages (pandas, openpyxl) - this happens once...
    python -m pip install -r requirements.txt
)

python -m monoamine_calc
if errorlevel 1 pause
endlocal

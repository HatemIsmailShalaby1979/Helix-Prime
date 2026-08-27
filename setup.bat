@echo off
echo ============================================
echo   Helix Prime - Operations Cockpit Setup
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Create virtual environment
echo [1/3] Creating virtual environment...
python -m venv .venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

REM Activate and install dependencies
echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r cockpit\requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/3] Setup complete!
echo.
echo ============================================
echo   To launch the cockpit, run:
echo     python launch.py
echo.
echo   Or directly:
echo     .venv\Scripts\streamlit run cockpit\cockpit.py
echo ============================================
pause

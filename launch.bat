@echo off
echo ============================================
echo   Helix Prime - Launch Operations Cockpit
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Running setup first...
    call setup.bat
)

echo Starting Operations Cockpit...
echo Browser will open to http://127.0.0.1:8501
echo Press Ctrl+C to stop.
echo.

.venv\Scripts\streamlit run cockpit\cockpit.py --server.headless=true --server.address=127.0.0.1

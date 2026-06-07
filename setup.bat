@echo off
echo ============================================
echo   Egon Trading Bot - Setup
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11 from python.org
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo Found Python:
python --version
echo.

:: Create virtual environment
if exist .venv (
    echo Virtual environment already exists, recreating...
    rmdir /s /q .venv
)

echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
.venv\Scripts\pip.exe install --upgrade pip >nul 2>&1
.venv\Scripts\pip.exe install MetaTrader5 pandas numpy pytz matplotlib
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Open MetaTrader5 and log in to your account
echo   2. Enable "Algo Trading" button in MT5 toolbar
echo   3. Make sure XAUUSD.p is visible in Market Watch
echo   4. Run start_egon_gui.bat to launch the dashboard
echo.
echo NOTE: If your broker uses a different gold symbol
echo       (not XAUUSD.p), edit these files:
echo       - src\core\mt5_client.py (line 31)
echo       - src\services\market_data.py (line 9)
echo.
pause

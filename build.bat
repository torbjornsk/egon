@echo off
echo ============================================
echo   Egon Trading Bot - Build Executable
echo ============================================
echo.

:: Check uv is available
uv --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv not found. Install from https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

:: Install PyInstaller if not present
uv pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    uv pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Building Egon.exe ...
echo.

uv run pyinstaller egon.spec --noconfirm

if errorlevel 1 (
    echo.
    echo ERROR: Build failed. Check output above for details.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Build complete!
echo ============================================
echo.
echo Output: dist\Egon\
echo.
echo To distribute:
echo   1. Zip the entire dist\Egon\ folder
echo   2. Send the zip to your friend
echo   3. They extract it and run Egon.exe
echo   4. MetaTrader5 must be installed and logged in
echo.
pause

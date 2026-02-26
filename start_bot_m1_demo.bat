@echo off
echo ========================================
echo   Gold Trading Bot - M1 SCALPING DEMO
echo ========================================
echo.
echo IMPORTANT: Make sure you are logged into a DEMO account in MT5!
echo.
echo Configuration: 15%% @ 25x leverage (375%% effective)
echo Expected: ~95 trades/day, 70%% return per 50 days
echo Max Drawdown: ~40%%
echo.
pause
echo.
echo Starting M1 scalping bot on DEMO account...
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Start the M1 bot
python live_trading_bot_m1.py

pause

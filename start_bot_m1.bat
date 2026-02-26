@echo off
echo ========================================
echo   Gold Trading Bot - M1 SCALPING
echo ========================================
echo.
echo WARNING: This is the AGGRESSIVE M1 scalping bot!
echo.
echo Configuration: 15%% @ 25x leverage (375%% effective)
echo Expected: ~95 trades/day, 70%% return per 50 days
echo Max Drawdown: ~40%%
echo.
echo IMPORTANT: Make sure M5 bot is NOT running on same account
echo            or reduce position sizes to avoid over-leverage
echo.
pause
echo.
echo Starting M1 scalping bot...
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Start the M1 bot
python live_trading_bot_m1.py

pause

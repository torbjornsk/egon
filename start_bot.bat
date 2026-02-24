@echo off
echo ========================================
echo   Gold Trading Bot - REAL MONEY
echo ========================================
echo.
echo WARNING: This bot will trade with REAL MONEY!
echo Make sure you understand the risks.
echo.
echo IMPORTANT: Confirm you are logged into your REAL account in MT5!
echo.
echo Current Configuration: 15%% @ 25x leverage (375%% effective)
echo Expected Return: ~16%% per month average
echo Max Drawdown: ~28%% worst case
echo Win Rate: 78.8%% (based on 33 test periods)
echo.
pause
echo.
echo Starting bot on REAL account...
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Start the bot
python live_trading_bot.py

pause

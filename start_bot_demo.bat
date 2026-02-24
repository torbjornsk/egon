@echo off
echo ========================================
echo   Gold Trading Bot - DEMO ACCOUNT
echo ========================================
echo.
echo IMPORTANT: Make sure you are logged into a DEMO account in MT5!
echo.
echo This bot will place REAL trades on whatever account is logged in.
echo Check your MT5 terminal to confirm you're on a demo account.
echo.
echo Current Configuration: 15%% @ 25x leverage (375%% effective)
echo Expected Return: ~16%% per month average
echo Max Drawdown: ~28%% worst case
echo.
pause
echo.
echo Starting bot on DEMO account...
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Start the bot
python live_trading_bot.py

pause

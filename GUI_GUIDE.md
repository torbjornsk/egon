# Trading Bot GUI - User Guide

## Overview
The Trading Bot GUI provides a simple graphical interface to monitor and control both M5 and M1 trading bots from a single window.

## Features

### 1. Dual Bot Control
- Start/Stop M5 bot independently
- Start/Stop M1 bot independently
- Both bots can run simultaneously

### 2. Live Dashboard (Per Bot)
Each bot displays:
- **Status**: Running or Stopped
- **Balance**: Current account balance
- **Equity**: Current equity (balance + open P/L)
- **Profit**: Current open position profit/loss (color-coded: green=profit, red=loss)
- **Positions**: Number of open positions (e.g., "1/2" means 1 out of 2 max)
- **RSI**: Current RSI value
- **Trend**: Market trend (UPTREND ^, DOWNTREND v, or SIDEWAYS -)
- **Signal**: Current entry signal (LONG, SHORT, or None)

### 3. Live Log Output
- Real-time log output for each bot
- Auto-scrolls to show latest messages
- Shows all bot activity including:
  - Market analysis
  - Entry/exit signals
  - Trade executions
  - Safety checks
  - Errors and warnings

### 4. Combined Status Bar
Shows totals across both bots:
- Total Equity
- Total Profit
- Active Positions (out of 4 max total)

## How to Use

### Starting the GUI
Double-click `start_gui.bat` or run:
```
python bot_gui.py
```

### Starting a Bot
1. Click "Start M5 Bot" or "Start M1 Bot"
2. The bot will initialize and connect to MT5
3. Dashboard will update with live data
4. Log output will show bot activity

### Stopping a Bot
1. Click "Stop M5 Bot" or "Stop M1 Bot"
2. The bot will terminate gracefully
3. Dashboard will freeze at last values
4. Status will show "Stopped"

### Monitoring
- Dashboard updates every 0.5 seconds
- Log output appears in real-time
- Profit values are color-coded for quick assessment
- Combined status bar shows overall performance

## Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                Trading Bot Control Panel                        │
├──────────────────────────┬──────────────────────────────────────┤
│  M5 Bot (5-min candles)  │  M1 Bot (1-min candles)             │
├──────────────────────────┼──────────────────────────────────────┤
│  Status: Running         │  Status: Running                     │
│  Balance: $10,500.00     │  Balance: $10,500.00                │
│  Equity: $10,550.00      │  Equity: $10,520.00                 │
│  Profit: $50.00          │  Profit: $20.00                     │
│  Positions: 1/2          │  Positions: 2/2                     │
│  RSI: 32.4               │  RSI: 28.1                          │
│  Trend: UPTREND ^        │  Trend: DOWNTREND v                 │
│  Signal: LONG            │  Signal: None                       │
├──────────────────────────┼──────────────────────────────────────┤
│  [Start] [Stop]          │  [Start] [Stop]                     │
├──────────────────────────┼──────────────────────────────────────┤
│  Log Output:             │  Log Output:                        │
│  ┌────────────────────┐  │  ┌────────────────────────────────┐ │
│  │ [M5 bot logs...]   │  │  │ [M1 bot logs...]               │ │
│  │                    │  │  │                                │ │
│  └────────────────────┘  │  └────────────────────────────────┘ │
├──────────────────────────┴──────────────────────────────────────┤
│  Combined Status:                                               │
│  Total Equity: $21,070.00 | Total Profit: $70.00 | Positions: 3/4│
└─────────────────────────────────────────────────────────────────┘
```

## Tips

### Best Practices
1. **Monitor Both Bots**: Keep an eye on both dashboards to see how they complement each other
2. **Check Logs**: Review log output to understand bot decisions
3. **Watch Profit Colors**: Green/red profit values give quick visual feedback
4. **Combined View**: Use the combined status bar to see total performance

### Troubleshooting
- **Bot won't start**: Check that MT5 is running and logged in
- **No data updating**: Ensure bot is connected to MT5 (check logs)
- **GUI freezes**: Close and restart the GUI (bots will continue running in background)
- **Logs not showing**: Check that Python output is not buffered

### Safety
- **Closing GUI**: Closing the GUI window will stop both bots
- **Emergency Stop**: Click Stop buttons to immediately terminate bots
- **Bot Independence**: Each bot operates independently with its own safety mechanisms

## Data Extraction

The GUI automatically parses log output to extract:
- Account information (balance, equity, profit)
- Position counts
- Market indicators (RSI, trend)
- Entry signals

This data is displayed in the dashboard in real-time without affecting bot performance.

## Requirements
- Python 3.8+
- tkinter (included with Python)
- Both bot files: `live_trading_bot.py` and `live_trading_bot_m1.py`
- MetaTrader 5 running and logged in

## Limitations
- GUI must remain open for bots to run
- Closing GUI stops both bots
- Historical data not preserved between GUI sessions
- Dashboard shows current state only (no charts or history)

## Future Enhancements
Potential additions:
- Performance charts
- Trade history table
- Configuration editor
- Alert notifications
- Export logs to file
- Restart bot button
- Pause/resume functionality

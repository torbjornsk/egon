# GUI Improvements V2

## Changes Made

### 1. Better Initial Sizing
- Changed from 1600x800 to 1400x900
- Better proportions for 2560x1440 resolution screens
- More vertical space for position cards and logs

### 2. Removed Middle Pane Scrollbar
- Dashboard is now non-scrollable
- All content fits in the window
- Cleaner, more professional look
- Better use of available space

### 3. Static Position Cards (2 per bot)
- Replaced scrollable position list with 2 fixed position card slots
- Each card shows:
  - Position ticket number and type (LONG/SHORT)
  - Current profit/loss with color coding
  - Entry price and time held
  - Exit signals section (new!)

### 4. Exit Signals Display
Each position card now shows 4 exit conditions:

#### For LONG Positions:
1. **RSI Exit**: Shows if RSI >= exit threshold (75)
2. **Take Profit**: Shows if price >= TP target
3. **Time Exit**: Shows if position held >10 min while losing (M1 only)
4. **Current P/L**: Shows percentage gain/loss

#### For SHORT Positions:
1. **RSI Exit**: Shows if RSI <= exit threshold (25)
2. **Take Profit**: Shows if price <= TP target
3. **Time Exit**: Shows if position held >10 min while losing (M1 only)
4. **Current P/L**: Shows percentage gain/loss

### 5. Visual Indicators
- ✅ = Condition met (exit signal active)
- ❌ = Condition not met
- ⚠ = Warning (time-based exit triggered)
- Color coding:
  - Green: Profitable positions, met conditions
  - Red: Losing positions, unmet conditions
  - Gray: Empty position slots

## Layout Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                    Gold Trading Bot Dashboard                    │
├──────────┬──────────────────────────────────────┬───────────────┤
│          │                                      │               │
│  M5 Log  │           Dashboard                  │    M1 Log     │
│          │                                      │               │
│  (400px) │  ┌────────────────────────────────┐  │    (400px)    │
│          │  │ Account Info (shared)          │  │               │
│          │  ├────────────────────────────────┤  │               │
│          │  │ Current Price (shared)         │  │               │
│          │  ├────────────────────────────────┤  │               │
│          │  │ M5 Bot                         │  │               │
│          │  │ ├─ Controls                    │  │               │
│          │  │ ├─ Market Indicators           │  │               │
│          │  │ ├─ Entry Conditions            │  │               │
│          │  │ └─ Positions (2 static cards)  │  │               │
│          │  │    ├─ Position 1 + Exit Signals│  │               │
│          │  │    └─ Position 2 + Exit Signals│  │               │
│          │  ├────────────────────────────────┤  │               │
│          │  │ M1 Bot                         │  │               │
│          │  │ ├─ Controls                    │  │               │
│          │  │ ├─ Market Indicators           │  │               │
│          │  │ ├─ Entry Conditions            │  │               │
│          │  │ └─ Positions (2 static cards)  │  │               │
│          │  │    ├─ Position 1 + Exit Signals│  │               │
│          │  │    └─ Position 2 + Exit Signals│  │               │
│          │  └────────────────────────────────┘  │               │
│          │                                      │               │
└──────────┴──────────────────────────────────────┴───────────────┘
```

## Benefits

1. **No wasted space**: Removed unnecessary scrollbars
2. **Better sizing**: Optimized for 2560x1440 screens
3. **Fixed layout**: 2 positions max = 2 static cards (no scrolling needed)
4. **Exit visibility**: Can see why positions might close before they do
5. **Cleaner design**: More professional, less cluttered
6. **Better information**: Exit signals help understand bot behavior

## Usage

Start the GUI as before:
```bash
python bot_gui.py
```

Or use the batch file:
```bash
start_gui.bat
```

The GUI will:
- Show 2 position card slots per bot (empty if no positions)
- Display exit signals for each open position
- Update in real-time every 1 second
- Work even when bots are stopped (fetches data from MT5 directly)

# Unicode Encoding Fix ✓

## Issue
Windows console (cp1252 encoding) can't display Unicode emoji characters like ⏸️ and ⏳, causing logging errors.

## Fixed
Replaced all Unicode emojis with plain ASCII text:

### Before
```
⏸️  Waiting for market to open...
⏳ Waiting for new candle...
```

### After
```
[WAITING] Market closed - last data: 2026-02-27 23:55, 2727min ago
[MONITORING] Waiting for new candle - current: 22:05, price: 5280.15
```

## Files Updated
- `live_trading_bot.py` (M5 bot)
- `live_trading_bot_m1.py` (M1 bot)
- `live_trading_bot_trend.py` (Trend bot)

## Benefits
- ✓ Works on all Windows systems
- ✓ No encoding errors
- ✓ Clear status messages
- ✓ Professional appearance

## Test
```bash
python live_trading_bot.py
```

Should now run without Unicode errors, showing:
```
[WAITING] Market closed - last data: 2026-02-27 23:55, 2727min ago
[WAITING] Market closed - last data: 2026-02-27 23:55, 2728min ago
...
```

All bots now use ASCII-only characters for maximum compatibility!

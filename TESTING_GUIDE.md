# Testing Guide for Refactored Bots

## Quick Verification

Run the test suite to verify all components are working:
```bash
python test_refactored_bots.py
```

All tests should pass before proceeding.

## Functional Testing

### 1. Test M5 Bot Startup

**Original bot:**
```bash
python live_trading_bot.py --config config/m5_params.json --interval 15
```

**Refactored bot:**
```bash
python live_trading_bot_refactored.py --config config/m5_params.json --interval 15
```

**What to verify:**
- ✓ Connects to MT5 successfully
- ✓ Shows account info (login, server, balance, leverage)
- ✓ Displays initial market state with indicators
- ✓ Shows "Market Status: OPEN" or "CLOSED" correctly
- ✓ Prints periodic status messages every 60 seconds
- ✓ Detects new M5 candles correctly
- ✓ No Unicode encoding errors (uses ASCII only)

### 2. Test M1 Bot Startup

**Original bot:**
```bash
python live_trading_bot_m1.py --config config/m1_params.json --interval 1
```

**Refactored bot:**
```bash
python live_trading_bot_m1_refactored.py --config config/m1_params.json --interval 1
```

**What to verify:**
- ✓ Connects to MT5 successfully
- ✓ Shows account info
- ✓ Displays initial market state with indicators
- ✓ Shows "Market Status: OPEN" or "CLOSED" correctly
- ✓ Prints periodic status messages every 60 seconds
- ✓ Detects new M1 candles correctly
- ✓ No Unicode encoding errors

### 3. Compare Startup Output

The startup output should be nearly identical between original and refactored bots.

**Expected startup sequence:**
```
================================================================================
M5 Scalping Bot Initialized
================================================================================
Configuration loaded: [strategy name]
Position Size: [X]%
Leverage: [Y]x
================================================================================
Connected to MT5
Account: [account number]
Server: [server name]
Balance: $[amount]
Leverage: 1:[leverage]

Fetching initial data...

Current Market State:
  Time: [timestamp]
  Close: [price]
  EMA Fast ([period]): [value]
  EMA Slow ([period]): [value]
  RSI: [value]
  ATR: [value]
  Trend: [UPTREND/DOWNTREND/SIDEWAYS]

  Market Status: [OPEN/CLOSED]
  [Monitoring for signals... / Waiting for market to open...]

================================================================================
M5 SCALPING BOT STARTED
================================================================================
Strategy: [strategy name]
Timeframe: M5 (5-minute candles)
Checking every 15 second(s) for new candles
================================================================================
```

### 4. Test Trading Logic (Market Open)

When market is open and a new candle forms:

**What to verify:**
- ✓ Detects new candles correctly
- ✓ Calculates indicators (EMA, RSI, ATR)
- ✓ Generates entry signals when RSI conditions met
- ✓ Places orders with correct SL/TP
- ✓ Tracks positions correctly
- ✓ Generates exit signals appropriately
- ✓ Closes positions when exit conditions met
- ✓ Respects cooldown periods after closing
- ✓ Enforces max position limits (2 positions)

### 5. Test Safety Mechanisms

**What to verify:**
- ✓ Drawdown limit check works
- ✓ Daily loss limit check works
- ✓ Consecutive loss tracking works
- ✓ Emergency equity threshold works
- ✓ Weekend close protection works (Friday before 5pm EST)
- ✓ Trading pauses when safety limits hit

### 6. Test Weekend Behavior

Run bots on Friday afternoon (EST):

**What to verify:**
- ✓ Detects approaching weekend close (30 min before)
- ✓ Closes all open positions before weekend
- ✓ Prevents new entries when weekend approaching
- ✓ Shows appropriate warning messages

### 7. Test Market Closed Behavior

Run bots when market is closed:

**What to verify:**
- ✓ Shows "Market Status: CLOSED"
- ✓ Displays last data timestamp and age
- ✓ Prints periodic status messages
- ✓ Doesn't attempt to trade
- ✓ Waits patiently for market to open

## Side-by-Side Comparison

For thorough testing, run both original and refactored bots simultaneously (in different terminals) and compare:

**Terminal 1 (Original M5):**
```bash
python live_trading_bot.py --config config/m5_params.json --interval 15
```

**Terminal 2 (Refactored M5):**
```bash
python live_trading_bot_refactored.py --config config/m5_params.json --interval 15
```

**Compare:**
- Startup messages should be identical
- New candle detection should happen at same time
- Entry/exit signals should match
- Position management should be identical
- Safety checks should trigger at same thresholds

## Known Differences (Expected)

The refactored bots should behave identically, but there may be minor cosmetic differences:

1. **Log messages**: Slightly different wording but same information
2. **Code organization**: Internal structure is different but behavior is same
3. **File names**: Different file names but same functionality

## Troubleshooting

### If bots behave differently:

1. **Check config files**: Ensure both use same config
2. **Check magic numbers**: M5=234000, M1=234001
3. **Check symbol**: Should be `XAUUSD.p` for Dominion Markets
4. **Check timeframes**: M5 uses 5-min, M1 uses 1-min
5. **Check logs**: Compare log files for differences

### If tests fail:

1. **Import errors**: Ensure `src/` directory exists with `__init__.py`
2. **Config errors**: Verify config files are valid JSON
3. **MT5 errors**: Ensure MT5 is installed and running
4. **Symbol errors**: Verify `XAUUSD.p` is available in MT5

## Migration Checklist

Once testing confirms refactored bots work correctly:

- [ ] All startup tests pass
- [ ] Trading logic matches original
- [ ] Safety mechanisms work correctly
- [ ] Weekend protection works
- [ ] No encoding errors
- [ ] Side-by-side comparison shows identical behavior
- [ ] Backup original bots to `backup/` folder
- [ ] Rename refactored bots to replace originals
- [ ] Update any scripts/docs that reference bot files
- [ ] Test one more time after migration
- [ ] Monitor first live session closely

## Rollback Plan

If issues are discovered after migration:

1. Stop refactored bots immediately
2. Restore original bots from backup:
   ```bash
   cp backup/live_trading_bot.py .
   cp backup/live_trading_bot_m1.py .
   ```
3. Restart original bots
4. Document the issue
5. Fix refactored bots
6. Re-test before attempting migration again

## Success Criteria

Refactored bots are ready for production when:

✓ All automated tests pass
✓ Startup behavior matches original
✓ Trading logic produces identical signals
✓ Safety mechanisms trigger correctly
✓ No encoding or runtime errors
✓ Side-by-side testing shows identical behavior
✓ At least 1 hour of successful operation in test environment

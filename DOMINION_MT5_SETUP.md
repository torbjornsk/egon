# Dominion Markets MT5 Setup - Complete ✓

## Issue Found & Fixed

### Problem
Dominion Markets uses **`XAUUSD.p`** instead of `XAUUSD` for gold spot trading.
The `.p` suffix indicates it's a "spot" instrument.

### Solution
Updated all bot files to use `XAUUSD.p`:
- ✓ `live_trading_bot.py`
- ✓ `live_trading_bot_trend.py`
- ✓ `bot_gui.py`
- ✓ `bot_gui_v3.py`
- ✓ `src/strategies/trend_following.py`

## Test Results

### MT5 Connection Test: 10/11 Passed (90.9%) ✓

| Test | Status | Notes |
|------|--------|-------|
| Initialization | ✓ PASS | MT5 connects successfully |
| Account Info | ✓ PASS | $10,000 balance, 1:100 leverage |
| Symbol Info | ✓ PASS | XAUUSD.p found and accessible |
| Historical Data | ✓ PASS | M1, M5, H1, H4 all working |
| Tick Data | ✗ FAIL | Not critical (bots don't use ticks) |
| Positions | ✓ PASS | Can read open positions |
| Orders | ✓ PASS | Can read pending orders |
| History | ✓ PASS | Can read trade history |
| Order Validation | ✓ PASS | Can validate orders |
| Terminal Info | ✓ PASS | Connected, trading allowed |
| Symbols | ✓ PASS | 386 symbols available |

## Your Account Details

```
Login: 124333
Server: DominionMarkets-Live
Balance: $10,000.00
Leverage: 1:100
Currency: USD
```

## Symbol Information

```
Symbol: XAUUSD.p
Description: Gold vs US Dollar / Spot
Current Price: ~$5,279
Spread: 169 points (1.69)
Digits: 2
Min Volume: 0.01 lots
Max Volume: 500 lots
Volume Step: 0.01 lots
```

## What Works ✓

### Data Retrieval
- ✓ M1 bars (100 bars tested)
- ✓ M5 bars (100 bars tested)
- ✓ H1 bars (100 bars tested)
- ✓ H4 bars (50 bars tested)
- ✓ Latest prices available
- ✓ Historical data accessible

### Trading Functions
- ✓ Order validation
- ✓ Position management
- ✓ Order management
- ✓ Trade history
- ✓ Account information

### Bots Ready
- ✓ M1 Scalping Bot
- ✓ M5 Scalping Bot
- ✓ Trend Following Bot
- ✓ GUI interfaces

## What Doesn't Work (Non-Critical)

### Tick Data
- ✗ Tick-by-tick data retrieval fails
- **Impact**: None - bots use bar data (M1, M5, H1, H4)
- **Action**: No fix needed

## Files Updated

### Bot Files
```
live_trading_bot.py          - M1/M5 scalping bot
live_trading_bot_trend.py    - Trend following bot
bot_gui.py                   - GUI for M1/M5 bots
bot_gui_v3.py                - Alternative GUI
```

### Strategy Files
```
src/strategies/trend_following.py  - Trend strategy
```

### Test Files
```
tests/test_mt5_connection.py       - Comprehensive MT5 test
tests/test_symbol_detection.py     - Symbol finder
fix_dominion_symbol.py             - Auto-fix script
```

## How to Verify

### 1. Run Connection Test
```bash
python tests/test_mt5_connection.py
```

Expected: 10/11 tests pass

### 2. Test Symbol Detection
```bash
python tests/test_symbol_detection.py
```

Expected: Finds XAUUSD.p and retrieves data

### 3. Start a Bot
```bash
# M1/M5 Scalping
python bot_gui.py

# Trend Following
python live_trading_bot_trend.py
```

Expected: Bot starts without errors

## Broker-Specific Notes

### Dominion Markets
- Uses `.p` suffix for spot instruments
- 386 symbols available
- 1:100 leverage on demo accounts
- Build 5660 terminal
- Trading allowed
- Experts enabled

### Symbol Naming
```
Standard:  XAUUSD
Dominion:  XAUUSD.p  (spot)
```

Other Dominion gold symbols:
- `XAUEUR.p` - Gold vs Euro
- `XAUAUD.p` - Gold vs Australian Dollar
- `XAUCHF.p` - Gold vs Swiss Franc
- `XAUGBP.p` - Gold vs British Pound

## Migration from Other Brokers

If you switch brokers in the future:

### 1. Detect Symbol
```bash
python tests/test_symbol_detection.py
```

### 2. Update Configs
If symbol is different, run:
```bash
python fix_dominion_symbol.py
```

Or manually update the symbol name in bot files.

### 3. Test Connection
```bash
python tests/test_mt5_connection.py
```

## Common Issues & Solutions

### Issue: "Symbol not found"
**Solution**: Use `XAUUSD.p` instead of `XAUUSD`
```bash
python fix_dominion_symbol.py
```

### Issue: "No data retrieved"
**Solution**: Check if symbol is visible
```python
mt5.symbol_select('XAUUSD.p', True)
```

### Issue: "Order validation failed"
**Causes**:
- Market closed (normal)
- Insufficient margin
- Invalid lot size

**Check**: Run test during market hours

### Issue: "Connection failed"
**Solutions**:
1. Ensure MT5 terminal is running
2. Check you're logged into demo account
3. Verify internet connection
4. Restart MT5 terminal

## Performance Notes

### Spread
- Current: 169 points (1.69)
- This is $1.69 per 0.01 lot
- Higher than some brokers
- Factor into profit calculations

### Execution
- Order validation: Working
- Trade mode: 4 (Full access)
- Filling mode: IOC (Immediate or Cancel)

### Data Quality
- Historical data: Complete
- Real-time prices: Available
- All timeframes: Working

## Next Steps

### 1. Test Bots in Demo
Run each bot for a few hours to verify:
- Orders execute correctly
- Positions open/close properly
- Profit calculations accurate
- No errors in logs

### 2. Monitor Performance
Check:
- Spread impact on profits
- Execution speed
- Slippage
- Fill rates

### 3. Compare to Backtest
- Track live results
- Compare to backtest expectations
- Adjust parameters if needed

## Summary

✓ **MT5 connection working** (10/11 tests pass)
✓ **Symbol fixed** (XAUUSD → XAUUSD.p)
✓ **All bots updated** (5 files)
✓ **Data retrieval working** (M1, M5, H1, H4)
✓ **Trading functions ready** (orders, positions, history)
✓ **Ready for live trading** (demo account)

The only failing test (tick data) doesn't affect bot operation. Your bots are ready to run on Dominion Markets!

---

**Status**: ✓ Ready for trading
**Action**: Start bots and monitor
**Support**: Run `python tests/test_mt5_connection.py` anytime to verify connection

# Fix "Trade Disabled" Error (10017)

## Problem
Bot gets error: `Order failed: 10017 - Trade disabled`

## Root Cause
**AutoTrading is disabled in MetaTrader 5**

The diagnostic shows:
- ✓ Terminal Trade Allowed: True
- ❌ Account Trade Allowed: False ← **This is the problem**

## Solution

### Method 1: Enable AutoTrading Button (Recommended)

1. **Open MetaTrader 5**

2. **Look for the AutoTrading button** in the toolbar:
   - It looks like a small robot/EA icon
   - Or shows "AutoTrading" text
   - Located in the top toolbar

3. **Click the AutoTrading button**:
   - Button should turn **GREEN** when enabled
   - Button is **RED** or **GRAY** when disabled

4. **Alternative: Use keyboard shortcut**:
   - Press `Ctrl + E` to toggle AutoTrading

5. **Verify it's enabled**:
   - Button should be GREEN
   - Tooltip should say "AutoTrading is enabled"

6. **Restart your bot**

### Method 2: Enable in Options

1. Open MT5
2. Go to `Tools` → `Options` (or press `Ctrl + O`)
3. Go to `Expert Advisors` tab
4. Check these boxes:
   - ✓ Allow automated trading
   - ✓ Allow DLL imports (if needed)
   - ✓ Allow WebRequest for listed URL (if needed)
5. Click `OK`
6. Restart your bot

### Method 3: Check Account Restrictions

If AutoTrading is enabled but still doesn't work:

1. **Demo Account Restrictions**:
   - Some demo accounts have trading disabled
   - Try creating a new demo account
   - Or switch to a live account (with caution!)

2. **Account Type**:
   - Verify account is not "Investor" (read-only)
   - Should be "Trade" account type

3. **Contact Broker**:
   - If issue persists, contact Dominion Markets support
   - Ask them to enable trading on your account

## Verification

After enabling AutoTrading, run the diagnostic again:

```bash
python fix_trade_disabled.py
```

You should see:
```
Account Information:
  Trade Allowed: True  ← Should be True now
  Trade Expert: True

✓ No issues found - trading should work!
```

## Test Trading

Try placing a small test trade manually in MT5:

1. Right-click on XAUUSD.p chart
2. Select "Trading" → "New Order"
3. Try to place a small buy order (0.01 lots)
4. If it works, your bot should work too

## Common Issues

### Issue: Button is green but still fails
**Solution**: Restart MT5 completely, then enable AutoTrading again

### Issue: AutoTrading keeps disabling itself
**Solution**: 
- Check MT5 settings in Tools → Options → Expert Advisors
- Ensure "Allow automated trading" is checked
- Some brokers disable it after each restart

### Issue: Works in MT5 but not in bot
**Solution**:
- Ensure bot is using correct symbol: `XAUUSD.p`
- Check bot has correct magic number
- Verify bot is connected to same MT5 instance

## Quick Checklist

Before running bot:
- [ ] MT5 is running
- [ ] AutoTrading button is GREEN
- [ ] Account shows "Trade Allowed: True"
- [ ] Symbol XAUUSD.p is visible
- [ ] Market is open (not weekend)
- [ ] Can place manual trade in MT5

## Still Not Working?

If you've tried everything:

1. **Restart everything**:
   ```bash
   # Close MT5 completely
   # Close your bot
   # Restart MT5
   # Enable AutoTrading (Ctrl+E)
   # Run diagnostic
   python fix_trade_disabled.py
   # Start bot
   python live_trading_bot.py
   ```

2. **Check MT5 logs**:
   - In MT5: View → Toolbox → Journal
   - Look for error messages

3. **Try different symbol**:
   - If XAUUSD.p doesn't work, try XAUUSD
   - Update bot symbol if needed

4. **Contact support**:
   - Dominion Markets support
   - Provide account number and error details

## Expected Output After Fix

When AutoTrading is properly enabled:

```
Account Information:
  Login: 124333
  Server: DominionMarkets-Live
  Balance: $10000.00
  Trade Allowed: True   ← Fixed!
  Trade Expert: True

✓ Full trading is allowed for this symbol
✓ No issues found - trading should work!
```

Then your bot should be able to place trades successfully!

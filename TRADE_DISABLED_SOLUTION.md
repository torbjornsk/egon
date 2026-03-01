# "Trade Disabled" Error - Complete Solution Guide

## Quick Fix (30 seconds)

If you get: `Order failed: 10017 - Trade disabled`

**Most common cause**: Using wrong password type!

### Check Your Password Type

MT5 has TWO passwords:
- **Master Password** → Trading ✅
- **Investor Password** → Read-only ❌

### Fix It

1. **File → Login to Trade Account** in MT5
2. Use your **MASTER password** (not investor)
3. Run: `python diagnose_trade_issue.py`
4. Should show: `Trade Allowed: True` ✅

Done! Your bot should work now.

---

## Detailed Troubleshooting

### Step 1: Run Diagnostic

```bash
python diagnose_trade_issue.py
```

### Step 2: Check the Output

#### If you see:
```
Account Information:
  Trade Allowed: False  ❌
```

**Possible causes:**
1. ⭐ Using investor password (most common)
2. AutoTrading disabled
3. Demo account restrictions
4. Broker-side limitations

#### If you see:
```
Account Information:
  Trade Allowed: True  ✅
```

**Your account is fine!** Issue is elsewhere:
- Check symbol is correct (XAUUSD.p)
- Check market is open
- Check bot code for errors

### Step 3: Apply Solution

#### Solution A: Wrong Password (Most Common)

**Problem**: Using investor (read-only) password

**Fix**:
1. Find your master password (check registration email)
2. File → Login to Trade Account in MT5
3. Enter master password
4. Verify with diagnostic

See: `MT5_PASSWORD_TYPES.md`

#### Solution B: AutoTrading Disabled

**Problem**: AutoTrading button is off

**Fix**:
1. Look for AutoTrading button in MT5 toolbar (🤖)
2. Click it to enable (should turn green)
3. Or press Ctrl+E

See: `FIX_AUTOTRADING.md`

#### Solution C: Demo Account Restrictions

**Problem**: Demo account has trading disabled

**Fix**:
1. Create new demo account
2. Or contact Dominion Markets support
3. Or switch to live account (caution!)

See: `DEMO_ACCOUNT_TRADING_DISABLED.md`

---

## Verification

After applying fix, verify it works:

```bash
python diagnose_trade_issue.py
```

Should show:
```
Account Information:
  Trade Allowed: True  ✅
  Trade Expert: True   ✅
  
Terminal Information:
  Trade Allowed: True  ✅
  
Symbol Information:
  Trade Mode: FULL     ✅
  
✓ No critical issues found!
```

---

## Test Your Bot

```bash
python live_trading_bot.py --config config/m5_params.json --interval 15
```

When signal appears, should see:
```
>>> TRADE OPENED [LONG]
  Entry Price: $5353.02
  Stop Loss: $5343.02
  Take Profit: $5363.02
  Volume: 0.15 lots
  Order ID: 123456
```

---

## Common Issues & Solutions

### Issue: "Trade disabled" even with master password

**Check**:
- AutoTrading button is green
- Market is open (not weekend)
- Symbol XAUUSD.p exists
- Try manual trade in MT5 first

### Issue: Can view but can't trade

**Cause**: Using investor password

**Fix**: Login with master password

### Issue: AutoTrading keeps disabling

**Cause**: MT5 settings

**Fix**: 
- Tools → Options → Expert Advisors
- Check "Allow automated trading"
- Restart MT5

### Issue: Works in MT5 but not in bot

**Check**:
- Bot using correct symbol (XAUUSD.p)
- Bot connected to same MT5 instance
- No errors in bot logs

---

## Prevention

To avoid this issue in the future:

1. **Save master password** in password manager
2. **Label passwords clearly**: "Master (Trading)" vs "Investor (Read-only)"
3. **Verify after login**: Run diagnostic to confirm Trade Allowed: True
4. **Check AutoTrading**: Ensure green button before running bot
5. **Test manually**: Place test trade in MT5 before running bot

---

## Quick Reference

| Symptom | Cause | Solution |
|---------|-------|----------|
| Trade Allowed: False | Wrong password | Use master password |
| Trade Allowed: False | AutoTrading off | Enable AutoTrading (Ctrl+E) |
| Trade Allowed: False | Account restriction | Create new account |
| Trade Allowed: True | Symbol issue | Check XAUUSD.p exists |
| Trade Allowed: True | Market closed | Wait for market open |

---

## Documentation Files

- `MT5_PASSWORD_TYPES.md` - Password types explained
- `FIX_AUTOTRADING.md` - AutoTrading button fix
- `AUTOTRADING_QUICK_FIX.md` - Quick visual guide
- `DEMO_ACCOUNT_TRADING_DISABLED.md` - Account restrictions
- `diagnose_trade_issue.py` - Diagnostic tool
- `fix_trade_disabled.py` - Basic diagnostic

---

## Still Need Help?

1. **Run full diagnostic**: `python diagnose_trade_issue.py`
2. **Check all docs** listed above
3. **Try manual trade** in MT5 first
4. **Contact support**: support@dominionmarkets.com

---

## Success Checklist

Before running your bot:
- [ ] Logged in with master password
- [ ] AutoTrading button is green
- [ ] Diagnostic shows Trade Allowed: True
- [ ] Symbol XAUUSD.p is visible
- [ ] Market is open (not weekend)
- [ ] Manual trade works in MT5
- [ ] Bot config is correct

If all checked ✅ → Your bot should work perfectly!

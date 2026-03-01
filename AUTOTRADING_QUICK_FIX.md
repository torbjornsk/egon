# AutoTrading Quick Fix

## The Problem
```
Order failed: 10017 - Trade disabled
```

## The Solution (30 seconds)

### Step 1: Find the AutoTrading Button

Look at the **top toolbar** in MetaTrader 5:

```
┌─────────────────────────────────────────────────────┐
│ File  View  Insert  Charts  Tools  Window  Help    │
├─────────────────────────────────────────────────────┤
│ [📁] [💾] [🖨️] [📊] [🤖] ← AutoTrading button here │
│                        ↑                            │
│                   Click this!                       │
└─────────────────────────────────────────────────────┘
```

The button looks like:
- 🤖 A robot icon
- Or text saying "AutoTrading"
- Or "Algo Trading"

### Step 2: Check the Color

**RED/GRAY = Disabled** ❌
```
[🤖] ← Red or gray = Trading disabled
```

**GREEN = Enabled** ✅
```
[🤖] ← Green = Trading enabled
```

### Step 3: Click to Enable

Click the button once:
- Should turn **GREEN**
- Tooltip should say "AutoTrading is enabled"

**OR** press `Ctrl + E` on keyboard

### Step 4: Verify

Run the diagnostic:
```bash
python fix_trade_disabled.py
```

Should show:
```
Account Information:
  Trade Allowed: True  ✓
```

### Step 5: Restart Bot

```bash
python live_trading_bot.py
```

## Done! 🎉

Your bot should now be able to place trades.

---

## Still Not Working?

### Option A: Enable in Settings

1. Press `Ctrl + O` (Options)
2. Go to "Expert Advisors" tab
3. Check ✓ "Allow automated trading"
4. Click OK
5. Restart MT5

### Option B: Check Account Type

Your account might be:
- ❌ Investor account (read-only)
- ❌ Demo with restrictions
- ✅ Should be: Trade account

### Option C: Contact Broker

If nothing works:
- Contact Dominion Markets support
- Tell them: "AutoTrading is disabled on my account"
- Provide account number: 124333

---

## Visual Guide

### Before (Disabled):
```
MT5 Toolbar: [🤖] ← RED/GRAY
Bot Error:   Order failed: 10017 - Trade disabled
Status:      ❌ Cannot trade
```

### After (Enabled):
```
MT5 Toolbar: [🤖] ← GREEN
Bot Status:  >>> TRADE OPENED [LONG]
Status:      ✅ Trading works!
```

---

## Quick Test

After enabling, test manually in MT5:

1. Right-click chart
2. Trading → New Order
3. Try 0.01 lot buy order
4. If it works → Bot will work too!

---

## Remember

**Every time you restart MT5:**
- Check AutoTrading button is GREEN
- Some brokers disable it on restart
- Just click it again to enable

**Keyboard shortcut:** `Ctrl + E`

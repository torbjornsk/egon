# Demo Account Trading Disabled - Solution

## The Real Problem

Your diagnostic shows:
```
Account Information:
  Trade Allowed: False  ← This is the problem
  Trade Expert: True
  Account Type: DEMO
```

This is **NOT** an AutoTrading/AlgoTrading button issue. The demo account itself has trading disabled at the broker level.

## Why This Happens

The account shows `Trade Allowed: False`. This can happen when:

1. **Wrong password type** - Using investor (read-only) password instead of master password ⭐ MOST COMMON
2. **Demo account expired** - Demo accounts often have time limits (30-90 days)
3. **Account restrictions** - Some demo accounts are view-only
4. **Server-side limitation** - Broker disabled trading on this account
5. **Account type** - Account may be set as "Investor" (read-only) instead of "Trade"

## Solutions

### Solution 0: Check Password Type (Try This First!) ⭐

MT5 accounts have TWO passwords:
- **Master Password** - Full trading access ✅
- **Investor Password** - Read-only access ❌

If you're using the investor password, you'll get `Trade Allowed: False`.

**Fix:**
1. **File → Login to Trade Account** in MT5
2. **Enter your account number**
3. **Use MASTER password** (check your registration email)
4. **Select server**: DominionMarkets-Live
5. **Click Login**
6. **Run diagnostic** to verify: `python diagnose_trade_issue.py`

See `MT5_PASSWORD_TYPES.md` for more details.

### Solution 1: Create a New Demo Account

1. **Open MT5**
2. **File → Open an Account**
3. **Find Dominion Markets** in the broker list
4. **Select "Open a demo account"**
5. **Fill in the form**:
   - Name: Your name
   - Email: Your email
   - Account Type: Choose "Standard" or "ECN"
   - Leverage: 1:100 (or your preference)
   - Deposit: $10,000 (or your preference)
6. **Click "Next"** and complete registration
7. **Save the login credentials**
8. **Test trading** in the new account

### Solution 2: Contact Dominion Markets Support

If you want to keep using account 124333:

**Email**: support@dominionmarkets.com
**Subject**: "Demo Account Trading Disabled - Account 124333"

**Message template**:
```
Hello,

I have a demo account (Login: 124333) on DominionMarkets-Live server.
The account shows "Trade Allowed: False" and I cannot place any trades,
even though AutoTrading is enabled in MT5.

Could you please enable trading on this account, or let me know if I 
need to create a new demo account?

Thank you,
[Your Name]
```

### Solution 3: Switch to Live Account (Use Caution!)

If you're ready for live trading:

1. **Create a live account** with Dominion Markets
2. **Fund it** with real money (start small!)
3. **Test thoroughly** with small positions first
4. **Monitor closely** - real money is at risk

⚠️ **WARNING**: Only use live account if you:
- Have tested your strategy extensively
- Understand the risks
- Can afford to lose the money
- Have proper risk management in place

## Verify the New Account

After creating a new demo account, run the diagnostic:

```bash
python diagnose_trade_issue.py
```

You should see:
```
Account Information:
  Trade Allowed: True  ← Should be True now!
  Account Type: DEMO
```

## Test Trading Manually

Before running your bot:

1. **Open MT5** with new account
2. **Right-click** on XAUUSD.p chart
3. **Trading → New Order**
4. **Try placing** a small order (0.01 lots)
5. **If it works** → Your bot will work too!

## Update Your Bot

If you created a new account, you don't need to change anything in the bot code. Just:

1. Make sure MT5 is logged into the new account
2. Verify AutoTrading is enabled (green button)
3. Run your bot

## Why AutoTrading Button Didn't Help

The AutoTrading button controls whether **MT5 allows external programs** to trade.

But in your case:
- ✓ AutoTrading is enabled (Terminal Trade Allowed: True)
- ✓ Symbol trading is enabled (Trade Mode: FULL)
- ✓ Market is open (valid prices)
- ❌ **Account itself** has trading disabled (broker-side)

So the AutoTrading button is working correctly - the problem is at the account level.

## Quick Comparison

### Working Demo Account:
```
Account Trade Allowed: True  ✓
Terminal Trade Allowed: True ✓
Symbol Trade Mode: FULL      ✓
Result: Trading works! 🎉
```

### Your Current Account:
```
Account Trade Allowed: False ❌  ← Problem here
Terminal Trade Allowed: True ✓
Symbol Trade Mode: FULL      ✓
Result: Error 10017 - Trade disabled
```

## Next Steps

1. **Create new demo account** (5 minutes)
2. **Run diagnostic** to verify it works
3. **Test manual trade** in MT5
4. **Run your bot**

The new account should work immediately!

## Still Having Issues?

If the new demo account also shows `Trade Allowed: False`:

1. **Check account type** - Make sure it's "Trade" not "Investor"
2. **Try different server** - Dominion may have multiple demo servers
3. **Contact support** - There may be a regional restriction
4. **Check broker website** - May have specific demo account requirements

## Summary

- ❌ Current account (124333): Trading disabled by broker
- ✓ AutoTrading button: Working correctly
- ✓ Solution: Create new demo account
- ⏱️ Time to fix: 5 minutes

Good luck! The new account should work perfectly.

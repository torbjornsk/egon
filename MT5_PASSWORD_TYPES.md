# MT5 Password Types - Important!

## The Issue

If you get "Trade disabled" error (10017) even with AutoTrading enabled, you might be using the wrong password type.

## Two Password Types

MT5 accounts have **TWO different passwords**:

### 1. Master Password (Trading Password)
- ✅ **Full trading access**
- ✅ Can place, modify, and close orders
- ✅ Can change account settings
- ✅ Shows `Trade Allowed: True`
- **Use this for your trading bot!**

### 2. Investor Password (Read-Only)
- ❌ **Read-only access**
- ❌ Cannot place or modify orders
- ✅ Can view positions and history
- ✅ Can view charts and indicators
- ❌ Shows `Trade Allowed: False`
- **Do NOT use this for trading!**

## How to Check Which Password You're Using

Run the diagnostic:
```bash
python diagnose_trade_issue.py
```

Look for:
```
Account Information:
  Trade Allowed: True   ← Master password ✓
  Trade Allowed: False  ← Investor password ❌
```

## How to Switch to Master Password

### In MT5:

1. **File → Login to Trade Account**
2. **Enter your account number**
3. **Enter MASTER password** (not investor password)
4. **Select server**: DominionMarkets-Live
5. **Click Login**

### Finding Your Master Password

Check your account registration email from Dominion Markets:
```
Account: 124333
Server: DominionMarkets-Live
Master Password: [your trading password]
Investor Password: [read-only password]
```

**Use the Master Password for trading!**

## Why Two Passwords?

The investor password is useful for:
- Sharing account view with others (without trading access)
- Monitoring accounts without risk of accidental trades
- Portfolio managers showing performance to clients
- Educational purposes (students viewing teacher's account)

But for **automated trading**, you MUST use the **Master Password**.

## Common Mistake

When setting up MT5, it's easy to accidentally save the investor password instead of the master password. This causes:

```
Error: Order failed: 10017 - Trade disabled
Reason: Using investor (read-only) password
Solution: Login with master password
```

## Verify You're Using Master Password

After logging in with master password:

```bash
python diagnose_trade_issue.py
```

Should show:
```
Account Information:
  Trade Allowed: True  ✓
  Trade Expert: True   ✓
  
✓ No critical issues found!
```

## Security Note

**Keep your master password secure!**
- Never share it publicly
- Don't commit it to git
- Store it safely (password manager)
- Only use investor password for read-only access

## Quick Reference

| Password Type | Trading | Viewing | Bot Usage |
|--------------|---------|---------|-----------|
| Master       | ✅ Yes  | ✅ Yes  | ✅ Use this |
| Investor     | ❌ No   | ✅ Yes  | ❌ Don't use |

## Summary

If you get "Trade disabled" error:
1. Check if you're using investor password
2. Login with master password instead
3. Run diagnostic to verify
4. Bot should work immediately!

---

**Remember**: Master password = Trading ✅ | Investor password = Read-only ❌

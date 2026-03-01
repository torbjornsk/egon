# Leverage Quick Reference

## Your Setup

```
Account Leverage: 1:100 (Dominion MetaTrader)
                   ↓
         Maximum Allowed
                   ↓
Bot Leverage:  20-27x (Your bots)
                   ↓
         What You Actually Use
                   ↓
Actual Leverage: 2-5x (Real exposure)
```

## The Numbers

| Bot | Bot Leverage | Position Size | Actual Leverage |
|-----|--------------|---------------|-----------------|
| Trend | 20x | 10% | ~2.0x |
| M1 | 25x | 15% | ~3.75x |
| M5 | 27x | 18% | ~4.86x |

**All well below your 100x account limit** ✓

## Real Example ($10,000 account)

### M5 Bot Opens a Trade
```
Balance:           $10,000
Position Size:     18% = $1,800
Bot Leverage:      27x
Position Value:    $1,800 × 27 = $48,600
Required Margin:   $48,600 / 100 = $486
Free Margin:       $10,000 - $486 = $9,514

Actual Leverage:   4.86x
Safety Buffer:     95.14x unused
```

## Is This Safe?

### ✓ YES

- **Account leverage (100x)** = Just a limit
- **Bot leverage (20-27x)** = Conservative
- **Actual usage (2-5x)** = Very safe
- **Buffer**: 73-80x unused capacity

## What Each Leverage Means

### Account Leverage (100x)
- Maximum you CAN use
- Set by broker
- Like a credit limit
- **You don't use it all**

### Bot Leverage (20-27x)
- What bots WILL use
- Set in config files
- Like your spending budget
- **This determines risk**

### Actual Leverage (2-5x)
- What you REALLY use
- Calculated: (Position Size % × Bot Leverage)
- Your real exposure
- **This is your actual risk**

## Risk Comparison

| Trader Type | Typical Leverage | Your Bots |
|-------------|------------------|-----------|
| Reckless Retail | 50-100x | ✗ |
| Typical Retail | 20-50x | ✗ |
| **Your Bots** | **2-5x actual** | **✓** |
| Conservative Pro | 2-10x | ✓ |
| Institutional | 1-5x | ✓ |

**You're in the safe zone** ✓

## Margin Call Risk

### When It Happens
```
Margin Level = (Equity / Used Margin) × 100%

Safe:     > 200%
Warning:  < 100%
Danger:   < 50%
```

### Your Safety
```
With $10,000 and all 3 bots running:
- Total positions: ~$100,000
- Required margin: ~$1,000
- Margin level: 1000%

You'd need to lose $9,000 (90%) to hit danger zone.
```

## Quick Checks

### In MetaTrader Terminal
Look for:
- **Margin Level**: Should be > 200%
- **Free Margin**: Should be > $5,000 (for $10k account)
- **Equity**: Should be close to Balance (if no open trades)

### Red Flags
- Margin Level < 100%
- Free Margin < $1,000
- Can't open new positions

## What to Do

### Normal Operation
- **Nothing** - bots manage leverage automatically
- Monitor margin level occasionally
- Let bots do their thing

### If Concerned
- Check margin level in MT5
- Review open positions
- Verify bots are following config

### To Reduce Risk
Edit config files:
```json
{
  "leverage": 15,        // Lower from 20-27
  "position_size_pct": 0.10  // Lower from 0.15-0.18
}
```

### To Increase Risk (Not Recommended)
- Increase bot leverage
- Increase position size
- **Only if you know what you're doing**

## Key Points

1. **100x account leverage** = Maximum ceiling (not what you use)
2. **20-27x bot leverage** = What bots are configured to use
3. **2-5x actual leverage** = Your real exposure
4. **You're safe** - Well below limits
5. **No action needed** - Bots manage it automatically

## Summary

Your account leverage (100x) is like having a $100,000 credit card limit. Your bots only spend $2,000-5,000 of it. You're using credit responsibly with a huge safety buffer.

**Status**: ✓ Safe and well-configured
**Action**: None required

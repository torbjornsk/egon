# Leverage Explained - Account vs Bot Settings

## Your Situation

- **Account Leverage**: 1:100 (Dominion MetaTrader demo)
- **Bot Leverage Settings**:
  - M1 Bot: 25x
  - M5 Bot: 27x
  - Trend Bot: 20x

## What Does This Mean?

### Account Leverage (1:100)
This is the **maximum** leverage your broker allows. Think of it as your credit limit.

- **1:100 means**: For every $1 in your account, you can control up to $100 worth of positions
- **Example**: With $10,000 balance, you could theoretically open positions worth up to $1,000,000
- **This is a LIMIT, not what you're forced to use**

### Bot Leverage (20x, 25x, 27x)
This is what your bots **actually use**. Think of it as how much you actually spend on your credit card.

- **25x means**: The bot uses $25 of position value for every $1 of your balance
- **Example**: With $10,000 balance and 25x leverage, bot opens positions worth $250,000
- **This is what determines your actual risk**

## The Relationship

```
Account Leverage (100x) = Maximum Allowed
                ↓
Bot Leverage (20-27x) = What You Actually Use
                ↓
Position Size = Balance × Bot Leverage
```

### Your Setup is SAFE ✓

Your bots use **20-27x leverage**, which is well below your account's **100x limit**. This is good!

## Real Example

Let's say you have $10,000 in your account:

### M5 Bot (27x leverage, 18% position size)
```
Balance: $10,000
Position Size %: 18% = $1,800
Bot Leverage: 27x
Position Value: $1,800 × 27 = $48,600

Actual Leverage Used: 48,600 / 10,000 = 4.86x
```

### Trend Bot (20x leverage, 10% position size)
```
Balance: $10,000
Position Size %: 10% = $1,000
Bot Leverage: 20x
Position Value: $1,000 × 20 = $20,000

Actual Leverage Used: 20,000 / 10,000 = 2.0x
```

## Why This Matters

### 1. Margin Requirements
Your broker requires you to have enough margin (collateral) to open positions.

**Formula**: Required Margin = Position Value / Account Leverage

**Example** (M5 bot opening $48,600 position):
```
Required Margin = $48,600 / 100 = $486

You have $10,000, so you only need $486 locked as margin.
Remaining free margin: $10,000 - $486 = $9,514
```

### 2. Risk Per Trade
Higher leverage = bigger positions = more profit OR loss per pip.

**Example** (Gold at $2,700, 0.01 lot):
```
1 pip = $0.10 per 0.01 lot

With 27x leverage (M5 bot):
- Position: $48,600 = 0.18 lots
- 1 pip = $1.80
- 10 pip move = $18 profit/loss

With 20x leverage (Trend bot):
- Position: $20,000 = 0.074 lots
- 1 pip = $0.74
- 10 pip move = $7.40 profit/loss
```

### 3. Margin Call Risk
If your losses reduce your account below the required margin, you get a margin call.

**Your Safety Margin**:
```
Account Leverage: 100x (very high limit)
Bot Leverage: 20-27x (conservative usage)
Safety Buffer: 100 - 27 = 73x unused capacity

This means you can withstand significant drawdowns before margin call.
```

## Is Your Setup Safe?

### ✓ YES - Here's Why:

1. **Conservative Bot Leverage**
   - M1: 25x (vs 100x available)
   - M5: 27x (vs 100x available)
   - Trend: 20x (vs 100x available)

2. **Small Position Sizes**
   - M1: 15% of balance per trade
   - M5: 18% of balance per trade
   - Trend: 10% of balance per trade

3. **Actual Leverage Used**
   - M1: ~3.75x actual (15% × 25x)
   - M5: ~4.86x actual (18% × 27x)
   - Trend: ~2.0x actual (10% × 20x)

4. **Multiple Positions**
   - Even with 2-3 positions open, you're using ~10-15x actual leverage
   - Still well below your 100x limit

## Comparison to Other Traders

### Typical Retail Traders
- Often use 50-100x leverage
- Risk 50-100% of account on single trades
- High margin call risk

### Your Bots
- Use 20-27x leverage (conservative)
- Risk 10-18% per trade (controlled)
- Low margin call risk

### Professional Traders
- Often use 2-10x leverage
- Risk 1-5% per trade
- Very low margin call risk

**Your bots are between retail and professional - a good balance.**

## What If You Want to Change It?

### To Reduce Risk (More Conservative)
Lower the bot leverage in config files:

```json
// config/m5_params.json
{
  "leverage": 20,  // Was 27
  "position_size_pct": 0.15  // Was 0.18
}
```

This would reduce your actual leverage from ~4.86x to ~3.0x.

### To Increase Risk (More Aggressive)
You could increase bot leverage, but **NOT RECOMMENDED** unless:
- You have significant trading experience
- You're comfortable with higher drawdowns
- You understand the risks

### Account Leverage Change
You generally **don't need to change** your account leverage (100x). It's just a limit. Your bots control the actual usage.

## Key Takeaways

1. **Account Leverage (100x)** = Maximum allowed by broker
2. **Bot Leverage (20-27x)** = What bots actually use
3. **Actual Leverage (~2-5x)** = Real exposure (position size × bot leverage / balance)
4. **Your setup is SAFE** - Well below account limits
5. **Don't confuse the two** - Account leverage is a ceiling, bot leverage is actual usage

## Monitoring Your Leverage

### In MetaTrader
Check your terminal:
- **Balance**: Your account equity
- **Margin**: Amount locked in open positions
- **Free Margin**: Available for new positions
- **Margin Level**: (Equity / Margin) × 100%

**Safe Margin Level**: Above 200%
**Warning**: Below 100%
**Margin Call**: Below 50% (varies by broker)

### Your Bots
The bots automatically calculate position sizes based on:
1. Your current balance
2. Configured leverage (20-27x)
3. Position size percentage (10-18%)
4. Available margin

They won't open positions if insufficient margin.

## FAQ

### Q: Should I ask my broker to lower account leverage?
**A**: Not necessary. Your bots control actual usage. 100x is just a limit.

### Q: Can I use different leverage for different bots?
**A**: Yes! Each bot has its own leverage setting in its config file.

### Q: What happens if I run out of margin?
**A**: The bot will fail to open new positions. Existing positions remain open.

### Q: Is 100x account leverage dangerous?
**A**: Only if you use it all. Your bots use 20-27x, which is safe.

### Q: Should I increase bot leverage for more profit?
**A**: Not recommended. Higher leverage = higher risk. Current settings are optimized.

## Summary

Your **account leverage (100x)** is like having a $100,000 credit limit. Your **bot leverage (20-27x)** is like only spending $20,000-27,000 of it. You're using your credit responsibly, with plenty of buffer for safety.

The bots are configured conservatively and will manage risk automatically. You don't need to change anything unless you specifically want to be more or less aggressive.

---

**Current Setup**: ✓ Safe and well-configured
**Action Required**: None - bots will manage leverage automatically
**Recommendation**: Monitor margin levels in MT5 terminal

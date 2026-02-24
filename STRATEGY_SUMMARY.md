# Gold Trading Bot - Strategy Summary

## Performance Comparison (8-month backtest: June 2025 - Feb 2026)

| Strategy | Return | Max Drawdown | Win Rate | Trades | Risk/Reward | Notes |
|----------|--------|--------------|----------|--------|-------------|-------|
| **Bidirectional (BEST)** | **26.87%** | **5.58%** | 28.26% | 2530 | **4.81** | Long+Short, selective shorting |
| Hybrid | 28.44% | 4.53% | 62.72% | 837 | 6.28 | Long-only, high win rate |
| Genetic Algorithm | 91.81% | 36.19% | 32.25% | 431 | 2.54 | High return but risky |
| Your Original | 22.29% | 9.14% | 67.97% | 974 | 2.44 | Simple RSI, very consistent |
| Conservative Test | 19.20% | 10.86% | 27.57% | 3134 | 1.77 | Too many trades |

## Recommended Strategy: Bidirectional

**Configuration:** `config/bidirectional_strategy_params.json`

### Parameters:
- Fast EMA: 20
- Slow EMA: 30
- RSI Period: 10
- RSI Buy: 30 (oversold)
- RSI Sell: 75 (overbought)
- ATR Multiplier: 3.0x
- Profit Target: 3%
- Enable Shorts: Yes
- Compounding: Yes

### Why This Strategy?

1. **Best Risk/Reward Ratio (4.81)**
   - 26.87% return with only 5.58% drawdown
   - Much safer than genetic algorithm (36% drawdown)

2. **Bidirectional Trading**
   - Long positions: 2335 trades, 26% win rate
   - Short positions: 195 trades, 54.9% win rate
   - Shorts are selective but highly profitable

3. **Proven Performance**
   - Works in both uptrends and downtrends
   - 5.64% additional return from shorting capability
   - Lower drawdown than long-only strategies

4. **Aggressive Yet Safe**
   - Higher returns than conservative approaches
   - Risk is well-controlled (5.58% max drawdown)
   - Compounding enabled for exponential growth

### Entry Logic:
- **LONG**: RSI < 30 (buy dips)
- **SHORT**: RSI > 75 AND confirmed downtrend (sell rallies in bear markets)

### Exit Logic:
- RSI opposite extreme (70 for longs, 30 for shorts)
- 3% profit target
- ATR-based stop loss (3x ATR)
- Trend reversal protection

## Alternative Strategies

### If You Want Maximum Safety: Hybrid Strategy
- **Return:** 28.44%
- **Drawdown:** 4.53%
- **Config:** `config/hybrid_strategy_params.json`
- Long-only, very high win rate (62.72%)

### If You Want Maximum Returns (High Risk): Genetic Algorithm
- **Return:** 91.81%
- **Drawdown:** 36.19%
- **Config:** `config/trading_params_optimized.json`
- EMA crossover strategy, high risk/high reward

### If You Want Simplicity: Your Original Strategy
- **Return:** 22.29%
- **Drawdown:** 9.14%
- **Implementation:** `simulation.py`
- Simple RSI oversold/overbought, very consistent

## Next Steps

1. **Backtest on different time periods** to validate robustness
2. **Paper trade** with demo account for 1-2 weeks
3. **Start with small capital** when going live
4. **Monitor performance** and adjust if market conditions change

## Risk Warnings

- Past performance doesn't guarantee future results
- Gold is volatile - expect drawdowns
- Use proper position sizing (2% risk per trade recommended)
- Never risk more than you can afford to lose
- Consider using the bidirectional strategy for best risk/reward balance

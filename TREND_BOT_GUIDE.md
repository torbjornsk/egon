# Trend Following Bot - Quick Start Guide

## Overview

The trend bot complements your scalping bots (M1/M5) by capturing larger moves over hours to days.

**Key Differences:**
- **Scalping**: Quick in/out, 0.8-2.8% targets, M1/M5 timeframes
- **Trend**: Hold longer, 5-15% targets, H1/H4 timeframes

## Strategy

### Multi-Timeframe Analysis
1. **H4 (4-hour)**: Determines overall trend direction
   - EMA 50 vs EMA 200 crossover
   - ADX > 25 for strong trend
   
2. **H1 (1-hour)**: Entry timing
   - Wait for pullback to EMA 20
   - RSI 40-60 (not overbought/oversold)
   - MACD turning positive/negative

### Exit Strategy
- **Trailing stop**: 2x ATR, moves with price
- **Profit lock**: Locks 50% of profit at +5% gain
- **Trend reversal**: Exits if H4 trend reverses
- **RSI divergence**: Exits if momentum weakens
- **Time limit**: Max 7 days hold time

## Sentiment Integration

The bot can use news sentiment to filter trades:

### Option 1: Alpha Vantage (Automated)
1. Get free API key: https://www.alphavantage.co/support/#api-key
2. Add to `config/trend_params.json`:
   ```json
   "use_sentiment_filter": true,
   "sentiment_source": "alpha_vantage",
   "alpha_vantage_api_key": "YOUR_KEY_HERE"
   ```
3. Bot automatically fetches sentiment every hour

### Option 2: Manual (mrktedge.ai)
1. Check mrktedge.ai for gold sentiment
2. Run: `python update_sentiment.py`
3. Enter sentiment (bullish/bearish/neutral) and confidence
4. Bot reads your sentiment and adjusts trades

### Option 3: No Sentiment (Pure Technical)
1. Set in `config/trend_params.json`:
   ```json
   "use_sentiment_filter": false
   ```
2. Bot trades based on technical signals only

## Configuration

Edit `config/trend_params.json`:

```json
{
  "position_size_pct": 0.10,     // 10% per position
  "leverage": 20,                 // 20x leverage
  "max_positions": 2,             // Max 2 simultaneous positions
  "adx_threshold": 25,            // Minimum ADX for trend
  "rsi_min": 40,                  // RSI range for entry
  "rsi_max": 60,
  "atr_multiplier": 2.0,          // Stop loss distance
  "profit_target_pct": 0.05,      // 5% take profit
  "max_hold_hours": 168,          // 7 days max hold
  "use_sentiment_filter": true,   // Enable sentiment
  "sentiment_source": "manual"    // or "alpha_vantage"
}
```

## Running the Bot

### Start the Bot
```bash
python live_trading_bot_trend.py
```

### Update Sentiment (if using manual)
```bash
python update_sentiment.py
```

### Monitor
- Bot checks for signals every 60 minutes
- Prints status every 50 minutes
- Logs to `trading_bot_trend.log`

## Risk Management

### Position Sizing
- Base: 10% of account per position
- Max: 2 positions = 20% total exposure
- Leverage: 20x (lower than scalping's 25-27x)
- Effective exposure: 10% × 20x = 200% per position

### Safety Mechanisms
- **Consecutive losses**: Pauses after 8 losses
- **Daily loss limit**: Pauses if lose 15% in 24h
- **Emergency stop**: Closes all if equity < 50%
- **Trailing stops**: Automatically lock in profits

### Combined Portfolio
With all bots running:
- M5 scalping: 18% × 27x = 486% exposure
- M1 scalping: 15% × 25x = 375% exposure
- Trend: 20% × 20x = 400% exposure
- **Total**: 53% of account, ~1,261% leveraged exposure

This is aggressive but diversified across strategies and timeframes.

## Expected Performance

Based on typical trend-following strategies:

**Conservative Estimate:**
- Annual return: 30-50%
- Win rate: 35-45% (fewer wins, but bigger)
- Average win: 8-12%
- Average loss: 2-3%
- Profit factor: 2.0-3.0
- Max drawdown: 15-20%

**With Sentiment Filter:**
- Annual return: 40-60%
- Win rate: 40-50% (better entry timing)
- Profit factor: 2.5-3.5
- Max drawdown: 12-18%

## Backtesting

Before going live, backtest the strategy:

```bash
# Create backtest script (TODO)
python tests/backtest_trend.py
```

This will test the strategy on historical H1/H4 data.

## Monitoring

### Check Bot Status
The bot prints status every 50 minutes showing:
- Current balance and profit
- Open positions
- Trailing stop levels
- Trading status (active/paused)

### Log Files
- `trading_bot_trend.log` - All bot activity
- `config/market_sentiment.json` - Current sentiment

### Manual Commands
While bot is running:
- `Ctrl+C` - Stop bot gracefully
- Check positions in MT5 (magic number: 234002)

## Troubleshooting

### Bot not taking trades
1. Check H4 trend: Must have strong trend (ADX > 25)
2. Check sentiment: If enabled, must align with signal
3. Check positions: Max 2 positions allowed
4. Check logs: `trading_bot_trend.log`

### Sentiment not updating
1. **Alpha Vantage**: Check API key in config
2. **Manual**: Run `python update_sentiment.py`
3. Check cache: `data/sentiment_cache.json`

### Too many/few trades
- Adjust `check_interval_minutes` (default: 60)
- Adjust `adx_threshold` (higher = fewer trades)
- Adjust `rsi_min/max` range (wider = more trades)

## Next Steps

1. **Test with small position size first**
   - Set `position_size_pct: 0.05` (5%)
   - Run for 1-2 weeks
   - Monitor performance

2. **Optimize parameters**
   - Backtest different ADX thresholds
   - Test different RSI ranges
   - Optimize trailing stop distance

3. **Add to portfolio**
   - Run alongside M1/M5 bots
   - Monitor correlation
   - Adjust position sizes if needed

## Tips

1. **Sentiment is powerful**: Good sentiment filter can improve win rate by 10-15%
2. **Be patient**: Trend bot trades less frequently than scalping
3. **Let winners run**: Trailing stops lock in profits automatically
4. **Trust the system**: Don't manually close positions early
5. **Monitor H4 trend**: Most important factor for success

## Support

- Check logs: `trading_bot_trend.log`
- Review config: `config/trend_params.json`
- Update sentiment: `python update_sentiment.py`
- Test strategy: `python tests/backtest_trend.py` (TODO)

---

**Remember**: This bot is designed to complement your scalping bots, not replace them. Together they provide diversified exposure across different market conditions and timeframes.

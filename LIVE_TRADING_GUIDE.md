# Live Trading Bot - Setup Guide

## ⚠️ IMPORTANT WARNINGS

1. **Start with DEMO account** - Test thoroughly before using real money
2. **Monitor regularly** - Check the bot at least daily
3. **Understand the risks** - You can lose money, especially with leverage
4. **Have a stop-loss plan** - Know when to stop the bot
5. **Never risk more than you can afford to lose**

## Current Configuration

The bot is configured with the **Aggressive (15% @ 25x)** strategy:

- **Position Size:** 15% of balance per trade
- **Leverage:** 25x
- **Effective Position:** 375% of balance (3.75x leverage)
- **Expected Return:** ~150% over 8 months (based on backtest)
- **Max Drawdown:** ~30%
- **Win Rate:** 61%

## Prerequisites

1. **MetaTrader5** installed and running
2. **Demo or Live account** logged in to MT5
3. **Python environment** set up with dependencies

## Installation

```bash
# Install dependencies (if not already done)
uv pip install -e .

# Or with pip
pip install -e .
```

## Configuration Files

### Main Config: `config/safe_leveraged_params.json`

```json
{
  "strategy": "safe_leveraged",
  "position_size_pct": 0.15,
  "leverage": 25,
  "max_drawdown_limit": 0.35,
  "fast_ema": 20,
  "slow_ema": 30,
  "rsi_period": 10,
  "rsi_buy": 30,
  "rsi_sell": 75,
  "atr_multiplier": 3.0,
  "profit_target_pct": 0.03,
  "enable_shorts": true
}
```

### Alternative Configurations

- `config/safe_leveraged_params.json` - Aggressive (15% @ 25x) - **RECOMMENDED**
- `config/bidirectional_strategy_params.json` - Conservative (26% return, 5.5% DD)
- `config/hybrid_strategy_params.json` - Very Safe (28% return, 4.5% DD)

## Running the Bot

### 1. Test Connection First

```bash
python -c "import MetaTrader5 as mt5; print('MT5 OK' if mt5.initialize() else 'MT5 FAILED')"
```

### 2. Start the Bot

```bash
# Default configuration (Aggressive strategy)
python live_trading_bot.py

# With custom configuration
python live_trading_bot.py --config config/bidirectional_strategy_params.json

# With custom check interval (default is 60 seconds)
python live_trading_bot.py --interval 30

# Dry-run mode (for testing, no actual trades)
python live_trading_bot.py --dry-run
```

### 3. Monitor the Bot

The bot logs to both console and `trading_bot.log` file.

Watch for:
- Entry/exit signals
- Order execution confirmations
- Current balance and profit
- Drawdown percentage
- Any errors

## Safety Features

1. **Drawdown Limit:** Bot stops trading if drawdown exceeds 35%
2. **Position Sizing:** Only uses 15% of balance per trade
3. **Stop Losses:** Every trade has an ATR-based stop loss
4. **Take Profits:** 3% profit target on each trade
5. **Margin Call Protection:** Limits loss to position size

## Monitoring Checklist

### Daily
- [ ] Check bot is running
- [ ] Review trading_bot.log for errors
- [ ] Check current balance and drawdown
- [ ] Verify open positions in MT5

### Weekly
- [ ] Review trade performance
- [ ] Check win rate vs expected (should be ~60%)
- [ ] Verify drawdown is within limits (<35%)
- [ ] Adjust configuration if needed

### Monthly
- [ ] Calculate actual return vs expected
- [ ] Review largest wins/losses
- [ ] Consider rebalancing or adjusting strategy

## Stopping the Bot

1. Press `Ctrl+C` in the terminal
2. Bot will gracefully shutdown
3. Any open positions will remain (close manually if needed)

## Troubleshooting

### Bot won't connect to MT5
- Ensure MT5 is running
- Check you're logged in to an account
- Verify XAUUSD symbol is available

### No trades being placed
- Check RSI levels (need RSI < 30 for long, > 75 for short)
- Verify not in drawdown pause mode
- Check account has sufficient margin

### Orders failing
- Check account has free margin
- Verify symbol trading is allowed
- Check minimum lot size requirements

### High drawdown
- Consider switching to more conservative config
- Reduce position size or leverage
- Stop bot and reassess strategy

## Performance Expectations

Based on 8-month backtest (June 2025 - Feb 2026):

| Metric | Expected Value |
|--------|---------------|
| Return | ~150% over 8 months |
| Max Drawdown | ~30% |
| Win Rate | ~61% |
| Trades per Month | ~185 |
| Avg Win | ~$14 |
| Avg Loss | ~$20 |

**Note:** Past performance doesn't guarantee future results. Market conditions vary.

## Emergency Procedures

### If Drawdown Exceeds 40%
1. Stop the bot immediately
2. Close all open positions
3. Review what went wrong
4. Consider switching to conservative strategy

### If Account Balance Drops 50%
1. STOP TRADING
2. Withdraw remaining funds
3. Reassess risk tolerance
4. Only restart with money you can afford to lose

### If Unexpected Behavior
1. Stop the bot
2. Check trading_bot.log for errors
3. Verify MT5 connection
4. Test with dry-run mode first

## Support

For issues or questions:
1. Check trading_bot.log for error messages
2. Review this guide
3. Test with demo account first
4. Start with conservative configuration

## Disclaimer

This bot is provided for educational purposes. Trading involves substantial risk of loss. The developers are not responsible for any financial losses. Always:
- Start with demo accounts
- Only risk money you can afford to lose
- Monitor the bot regularly
- Understand the strategy before using
- Have a risk management plan

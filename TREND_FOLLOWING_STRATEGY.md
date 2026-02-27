# Trend Following Strategy Design

## Overview

A trend-following bot to complement your scalping bots by capturing larger moves. This strategy:
- **Scalping bots**: Quick in/out, mean reversion (M1/M5)
- **Trend bot**: Ride trends, hold longer positions (H1/H4)
- **Together**: Diversified approach covering different market conditions

## Strategy Concept: "Momentum Rider"

### Core Approach
1. **Identify strong trends** using multiple timeframe analysis
2. **Enter on pullbacks** within the trend (not at extremes)
3. **Trail stop loss** to lock in profits as trend continues
4. **Exit on trend reversal** signals

### Key Differences from Scalping
| Aspect | Scalping (M1/M5) | Trend Following (H1/H4) |
|--------|------------------|-------------------------|
| Hold Time | Minutes to hours | Hours to days |
| Target | 0.8-2.8% | 5-15% |
| Frequency | High (daily) | Low (weekly) |
| Market | Mean reversion | Trending |
| Position Size | 15-18% | 10-15% |

## Technical Implementation

### Entry Signals (Multi-Timeframe)

**H4 (4-hour) - Trend Direction**
- EMA 50 > EMA 200 = Uptrend
- EMA 50 < EMA 200 = Downtrend
- ADX > 25 = Strong trend

**H1 (1-hour) - Entry Timing**
- Price pulls back to EMA 20
- RSI 40-60 (not overbought/oversold)
- MACD histogram turning positive (for longs)

**Entry Conditions (LONG)**
```
1. H4 uptrend confirmed (EMA 50 > EMA 200, ADX > 25)
2. H1 pullback to EMA 20
3. H1 RSI between 40-60
4. H1 MACD turning up
5. Volume increasing
```

### Exit Strategy

**Trailing Stop Loss**
- Initial: 2x ATR below entry
- Trail: Move up as price rises (never down)
- Lock in: 50% of profit at +5%, trail remainder

**Exit Signals**
- Trailing stop hit
- H4 EMA crossover (trend reversal)
- RSI divergence (momentum weakening)
- Time-based: Close after 7 days regardless

### Position Sizing
- Base: 10% of account
- Max: 15% in strong trends
- Leverage: 20x (lower than scalping)
- Max 2 positions simultaneously

## News/Prediction Integration (mrktedge.ai)

### How to Use News Data

**Option 1: Sentiment Filter (Conservative)**
- Only take trades when news sentiment aligns with technical signal
- Example: Long signal + Bullish news = Enter
- Long signal + Bearish news = Skip

**Option 2: Confidence Booster (Moderate)**
- Increase position size when news confirms technical
- Base position: 10%
- With bullish news: 12-15%
- With bearish news: 7-8%

**Option 3: Early Entry (Aggressive)**
- Enter positions before technical signal if news is strong
- Requires high confidence predictions
- Smaller position size (5-7%)
- Tighter stop loss

### mrktedge.ai Integration Architecture

```python
class NewsIntegration:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.mrktedge.ai"
    
    def get_gold_sentiment(self):
        """Get current sentiment for gold"""
        # Returns: {'sentiment': 'bullish', 'confidence': 0.85, 'prediction': '+2.3%'}
        pass
    
    def should_trade(self, technical_signal, news_sentiment):
        """Decide if technical signal should be taken based on news"""
        if technical_signal == 'LONG' and news_sentiment['sentiment'] == 'bullish':
            return True, news_sentiment['confidence']
        elif technical_signal == 'SHORT' and news_sentiment['sentiment'] == 'bearish':
            return True, news_sentiment['confidence']
        else:
            return False, 0
    
    def adjust_position_size(self, base_size, confidence):
        """Adjust position size based on news confidence"""
        if confidence > 0.8:
            return base_size * 1.3  # 30% larger
        elif confidence > 0.6:
            return base_size * 1.1  # 10% larger
        else:
            return base_size * 0.8  # 20% smaller
```

## Risk Management

### Position Limits
- Max 2 trend positions
- Max 15% per position
- Total exposure: 30% (trend) + 33% (scalping) = 63% max

### Stop Loss Rules
- Initial: 2x ATR (typically 2-3% for gold)
- Never wider than 5%
- Trail as profit grows
- Emergency stop: -10% on position

### Drawdown Protection
- Pause new entries if account DD > 20%
- Reduce position size by 50% if DD > 15%
- Close all positions if DD > 30%

## Backtesting Strategy

Before going live, we need to:

1. **Implement the strategy** in `src/strategies/trend_following.py`
2. **Backtest on H1/H4 data** using your optimized test suite
3. **Test news integration** (if API available)
4. **Optimize parameters** (EMA periods, ADX threshold, etc.)
5. **Validate on recent data** (last 90 days)

## Expected Performance

Based on typical trend-following strategies on gold:

**Conservative Estimate**
- Annual return: 30-50%
- Win rate: 35-45% (fewer wins, but bigger)
- Average win: 8-12%
- Average loss: 2-3%
- Profit factor: 2.0-3.0
- Max drawdown: 15-20%

**With News Integration**
- Annual return: 40-60% (if news is accurate)
- Win rate: 40-50% (better entry timing)
- Profit factor: 2.5-3.5
- Max drawdown: 12-18% (avoid bad trades)

## Implementation Plan

### Phase 1: Basic Trend Following (No News)
1. Create `src/strategies/trend_following.py`
2. Implement H1/H4 multi-timeframe logic
3. Add trailing stop loss
4. Backtest on historical data
5. Optimize parameters

### Phase 2: News Integration (Optional)
1. Research mrktedge.ai API documentation
2. Create `src/integrations/mrktedge.py`
3. Implement sentiment filter
4. Test with paper trading
5. Validate news accuracy

### Phase 3: Live Deployment
1. Start with small position size (5%)
2. Monitor for 2 weeks
3. Gradually increase to 10-15%
4. Compare to backtest results

## Complementary to Scalping

### Portfolio Diversification

**Scalping Bots (M1/M5)**
- High frequency, small profits
- Mean reversion
- Works in ranging markets
- 33% of account

**Trend Bot (H1/H4)**
- Low frequency, large profits
- Momentum following
- Works in trending markets
- 15-30% of account

**Combined Benefits**
- Profit in all market conditions
- Reduced correlation
- Smoother equity curve
- Better risk-adjusted returns

### Risk Correlation

Scalping and trend following are negatively correlated:
- Scalping profits when market ranges
- Trend following profits when market trends
- Together: More consistent returns

## Questions to Answer

Before implementation:

1. **mrktedge.ai API**
   - Do you have API access?
   - What data format does it provide?
   - How often is it updated?
   - What's the historical accuracy?

2. **Timeframe Preference**
   - H1 (1-hour): More trades, shorter holds
   - H4 (4-hour): Fewer trades, longer holds
   - Daily: Even fewer, multi-day holds

3. **Risk Appetite**
   - Conservative: 10% position, no news
   - Moderate: 12% position, news filter
   - Aggressive: 15% position, news-driven entries

4. **Integration Priority**
   - Start with pure technical (no news)?
   - Or integrate news from day 1?

## Next Steps

1. **Decide on approach**: Pure technical or with news integration?
2. **Choose timeframe**: H1, H4, or Daily?
3. **Set risk parameters**: Position size, max drawdown, etc.
4. **Implement strategy**: I can create the code
5. **Backtest**: Validate before going live

Would you like me to:
- A) Start with pure technical trend following (no news)?
- B) Research mrktedge.ai API and integrate from the start?
- C) Create both versions and let you choose?

Also, what timeframe appeals to you most for trend following?

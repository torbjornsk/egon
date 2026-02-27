# Dynamic Position Sizing Integration Guide

## Overview

Volatility-adjusted position sizing improves risk-adjusted returns by:
- **Reducing position size during high volatility** (risk protection)
- **Increasing position size during low volatility** (profit optimization)

## Test Results

### M5 Bot
- Return: 40.1% (vs 43.1% fixed) - slightly lower
- Sharpe: 2.83 (vs 2.81 fixed) - **+0.6% improvement**
- Max DD: -5.0% (vs -5.8% fixed) - **better risk control**

### M1 Bot
- Return: 109.0% (vs 105.0% fixed) - **+4% improvement**
- Sharpe: 0.90 (vs 0.80 fixed) - **+12.3% improvement**
- Max DD: -12.6% (vs -12.9% fixed) - **better risk control**

## Integration Steps

### 1. Import the Module

```python
from src.position_sizing import PositionSizeCalculator
```

### 2. Initialize in Your Bot

```python
# In your bot's __init__ method
self.position_calculator = PositionSizeCalculator(
    strategy='volatility',
    base_position_pct=0.075,      # 7.5% base (your current setting)
    lookback_periods=100,          # 100 candles for volatility calculation
    high_vol_multiplier=0.6,       # 60% size in high volatility
    low_vol_multiplier=1.3         # 130% size in low volatility
)
```

### 3. Use When Opening Positions

Replace your current position sizing logic:

```python
# OLD CODE (fixed size):
position_size_pct = self.config['position_size_pct'] / 2  # 7.5%
lot_size = self.calculate_lot_size(position_size_pct)

# NEW CODE (dynamic size):
lot_size, position_pct, regime, info = self.position_calculator.get_position_size_for_trade(
    symbol=self.symbol,
    timeframe=self.timeframe,
    account_balance=self.account_info.balance,
    base_position_pct=self.config['position_size_pct'] / 2,
    leverage=self.config['leverage']
)

# Log the adjustment
self.logger.info(f"Position sizing: {regime} volatility, "
                f"adjusted from {info['base_position_pct']*100:.1f}% "
                f"to {position_pct*100:.1f}%, lot size: {lot_size:.2f}")
```

### 4. Example Integration for live_trading_bot_m1.py

```python
class M1TradingBot:
    def __init__(self, config_path='config/m1_params.json'):
        # ... existing init code ...
        
        # Add position size calculator
        self.position_calculator = PositionSizeCalculator(
            strategy='volatility',
            base_position_pct=self.config['position_size_pct'] / 2,
            lookback_periods=100,
            high_vol_multiplier=0.6,
            low_vol_multiplier=1.3
        )
    
    def open_position(self, signal_type):
        """Open a new position with dynamic sizing"""
        
        # Get dynamic position size
        lot_size, position_pct, regime, info = self.position_calculator.get_position_size_for_trade(
            symbol=self.symbol,
            timeframe=mt5.TIMEFRAME_M1,
            account_balance=self.account_info.balance,
            base_position_pct=self.config['position_size_pct'] / 2,
            leverage=self.config['leverage']
        )
        
        # Log volatility regime
        self.logger.info(f"Opening {signal_type} position:")
        self.logger.info(f"  Volatility: {regime} (ATR: {info['current_atr']:.2f})")
        self.logger.info(f"  Position size: {position_pct*100:.2f}% (base: {info['base_position_pct']*100:.2f}%)")
        self.logger.info(f"  Lot size: {lot_size:.2f}")
        
        # ... rest of your position opening logic ...
        # Use 'lot_size' instead of calculating it with fixed percentage
```

### 5. Example Integration for live_trading_bot.py (M5)

```python
class M5TradingBot:
    def __init__(self, config_path='config/m5_params.json'):
        # ... existing init code ...
        
        # Add position size calculator
        self.position_calculator = PositionSizeCalculator(
            strategy='volatility',
            base_position_pct=self.config['position_size_pct'] / 2,
            lookback_periods=100,
            high_vol_multiplier=0.6,
            low_vol_multiplier=1.3
        )
    
    def open_position(self, signal_type):
        """Open a new position with dynamic sizing"""
        
        # Get dynamic position size
        lot_size, position_pct, regime, info = self.position_calculator.get_position_size_for_trade(
            symbol=self.symbol,
            timeframe=mt5.TIMEFRAME_M5,
            account_balance=self.account_info.balance,
            base_position_pct=self.config['position_size_pct'] / 2,
            leverage=self.config['leverage']
        )
        
        # Log volatility regime
        self.logger.info(f"Opening {signal_type} position:")
        self.logger.info(f"  Volatility: {regime} (ATR: {info['current_atr']:.2f})")
        self.logger.info(f"  Position size: {position_pct*100:.2f}% (base: {info['base_position_pct']*100:.2f}%)")
        self.logger.info(f"  Lot size: {lot_size:.2f}")
        
        # ... rest of your position opening logic ...
```

## Configuration Options

### Conservative (Lower Risk)
```python
PositionSizeCalculator(
    strategy='volatility',
    base_position_pct=0.075,
    lookback_periods=100,
    high_vol_multiplier=0.5,   # More aggressive reduction
    low_vol_multiplier=1.2     # Less aggressive increase
)
```

### Aggressive (Higher Returns)
```python
PositionSizeCalculator(
    strategy='volatility',
    base_position_pct=0.075,
    lookback_periods=100,
    high_vol_multiplier=0.7,   # Less reduction
    low_vol_multiplier=1.5     # More increase
)
```

### Recommended (Balanced)
```python
PositionSizeCalculator(
    strategy='volatility',
    base_position_pct=0.075,
    lookback_periods=100,
    high_vol_multiplier=0.6,   # 60% in high vol
    low_vol_multiplier=1.3     # 130% in low vol
)
```

## Monitoring

Add to your GUI or logging to monitor the sizing:

```python
# In your status update method
sizing_info = self.position_calculator.sizer.get_position_size(current_atr)
adjusted_size, regime = sizing_info

print(f"Current Volatility Regime: {regime}")
print(f"Position Size Multiplier: {adjusted_size / base_size:.2f}x")
```

## Testing Before Live

1. **Backtest first**: Run `python tests/test_dynamic_sizing.py` to verify
2. **Paper trade**: Test on demo account for 1-2 weeks
3. **Monitor closely**: Watch the first few trades with dynamic sizing
4. **Compare results**: Track performance vs fixed sizing

## Rollback Plan

If you want to revert to fixed sizing:

```python
# Change strategy to 'fixed'
self.position_calculator = PositionSizeCalculator(
    strategy='fixed',
    base_position_pct=0.075
)
```

Or simply remove the calculator and use your original logic.

## Expected Impact

### M5 Bot
- Minimal return change (-3%)
- Slightly better Sharpe (+0.6%)
- Better drawdown control (-0.8%)
- **Recommendation**: Optional, marginal improvement

### M1 Bot
- Better returns (+4%)
- Significantly better Sharpe (+12.3%)
- Better drawdown control (-0.3%)
- **Recommendation**: Strongly recommended

## Safety Notes

1. The system still respects your max drawdown limits
2. Position sizes are capped at 2x base (130% max multiplier)
3. Minimum position size is 60% of base (never goes below)
4. ATR calculation uses 100-candle lookback for stability
5. All existing stop losses and safety mechanisms remain active

## Questions?

- Test results: `tests/test_dynamic_sizing.py`
- Risk analysis: `tests/analyze_risk.py`
- Implementation: `src/position_sizing.py`

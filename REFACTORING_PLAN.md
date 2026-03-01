# Bot Refactoring Plan

## Current Problem

You're absolutely right - there's significant code duplication:

### Duplicate Code Between Bots:
- `live_trading_bot.py` (M5 scalping) - ~1050 lines
- `live_trading_bot_m1.py` (M1 scalping) - ~1150 lines
- `live_trading_bot_trend.py` (Trend following) - ~500 lines

### What's Duplicated:
- MT5 connection/disconnection
- Account info retrieval
- Historical data fetching
- Position management (open/close)
- Safety checks (drawdown, daily loss, consecutive losses)
- Emergency close logic
- Weekend close protection
- Logging setup
- Main run loop
- Status printing

### What's Different:
- Indicator calculations (EMA periods, RSI settings)
- Signal generation logic
- Entry/exit rules
- Timeframes (M1 vs M5 vs H1/H4)

## Proposed Solution

### 1. Base Class (DONE ✓)
Created `src/base_trading_bot.py` with:
- MT5 connection management
- Account info retrieval
- Historical data fetching
- Position management
- Safety checks
- Main run loop
- Logging infrastructure
- Status printing

### 2. Strategy Classes (Separate)
Keep strategy-specific logic in:
- `src/strategies/scalping.py` - M5 scalping strategy
- `src/strategies/m1_scalping.py` - M1 scalping strategy  
- `src/strategies/trend_following.py` - Trend strategy

### 3. Refactored Bot Files
Simplify to:
- `live_trading_bot.py` - Inherits from BaseTradingBot, uses ScalpingStrategy
- `live_trading_bot_m1.py` - Inherits from BaseTradingBot, uses M1ScalpingStrategy
- `live_trading_bot_trend.py` - Already uses TrendFollowingStrategy

## Benefits

### Code Reduction
- M5 bot: 1050 lines → ~200 lines (80% reduction)
- M1 bot: 1150 lines → ~200 lines (82% reduction)
- Shared code: ~800 lines in base class

### Maintainability
- Fix bugs once in base class
- Add features once (affects all bots)
- Easier to test
- Clearer separation of concerns

### Consistency
- All bots use same logging format
- All bots have same safety checks
- All bots have same status messages
- All bots handle errors the same way

## Implementation Steps

### Phase 1: Extract Strategy Logic (Recommended First)
1. Create `src/strategies/m1_scalping.py`
2. Move M1-specific indicator calculation there
3. Move M1-specific signal generation there
4. Test M1 bot still works

### Phase 2: Refactor M5 Bot
1. Update `live_trading_bot.py` to inherit from `BaseTradingBot`
2. Move strategy logic to `src/strategies/scalping.py`
3. Test M5 bot still works

### Phase 3: Refactor M1 Bot
1. Update `live_trading_bot_m1.py` to inherit from `BaseTradingBot`
2. Use `src/strategies/m1_scalping.py`
3. Test M1 bot still works

### Phase 4: Refactor Trend Bot (Optional)
1. Update `live_trading_bot_trend.py` to inherit from `BaseTradingBot`
2. Already uses `src/strategies/trend_following.py`
3. Test trend bot still works

### Phase 5: Cleanup
1. Remove duplicate code
2. Update documentation
3. Update tests

## Example: Refactored M5 Bot

### Before (1050 lines)
```python
class LiveTradingBot:
    def __init__(self, config_path):
        # 50 lines of initialization
        
    def connect_mt5(self):
        # 20 lines
        
    def get_account_info(self):
        # 15 lines
        
    def get_historical_data(self):
        # 25 lines
        
    def compute_indicators(self, df):
        # 40 lines of indicator calculation
        
    def check_drawdown(self):
        # 20 lines
        
    # ... 900 more lines
```

### After (~200 lines)
```python
from src.base_trading_bot import BaseTradingBot
from src.strategies.scalping import ScalpingStrategy

class M5ScalpingBot(BaseTradingBot):
    def __init__(self, config_path='config/m5_params.json'):
        super().__init__(
            config_path=config_path,
            magic_number=234000,
            strategy_name="M5 Scalping"
        )
        self.strategy = ScalpingStrategy(self.config)
    
    def get_timeframe(self):
        return mt5.TIMEFRAME_M5
    
    def compute_indicators(self, df):
        return self.strategy.calculate_indicators(df)
    
    def print_indicators(self, latest, df):
        logging.info(f"  EMA 5: {latest['ema_5']:.2f}")
        logging.info(f"  EMA 12: {latest['ema_12']:.2f}")
        logging.info(f"  RSI: {latest['rsi']:.2f}")
        logging.info(f"  ATR: {latest['atr']:.2f}")
    
    def trading_logic(self):
        # Get data
        df = self.get_historical_data()
        if df is None:
            return
        
        # Calculate indicators
        df = self.compute_indicators(df)
        
        # Run safety checks
        self.run_safety_checks()
        if self.trading_paused:
            return
        
        # Check weekend close
        is_weekend, reason = self.is_near_weekend_close()
        if is_weekend:
            self.emergency_close_all()
            return
        
        # Generate signals and trade
        signals = self.strategy.generate_signals(df)
        self.execute_signals(signals)
```

## Recommendation

### Do This Refactoring?
**Pros:**
- Much cleaner code
- Easier to maintain
- Consistent behavior
- Easier to add new bots

**Cons:**
- Takes time to refactor
- Risk of breaking something
- Need to test thoroughly

### My Recommendation:
**Yes, but incrementally:**
1. Start with Phase 1 (extract M1 strategy)
2. Test thoroughly
3. Then do Phase 2 (refactor M5)
4. Test thoroughly
5. Continue if all works well

### Alternative: Keep As-Is
If the bots are working and you don't plan to add more bots or make frequent changes, you could keep the current structure. The duplication is not ideal but it's functional.

## Next Steps

Would you like me to:
1. **Do the full refactoring** (will take time, but cleaner result)
2. **Do Phase 1 only** (extract M1 strategy, minimal risk)
3. **Leave as-is** (bots work, don't fix what isn't broken)
4. **Something else**

Let me know your preference!

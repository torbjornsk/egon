# Refactored Bot Architecture

## Overview

The refactored architecture separates shared infrastructure from strategy-specific logic, eliminating code duplication and improving maintainability.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     BaseTradingBot                              │
│                  (src/base_trading_bot.py)                      │
├─────────────────────────────────────────────────────────────────┤
│  Shared Infrastructure (450 lines)                              │
│                                                                 │
│  • MT5 Connection Management                                    │
│  • Account Information Retrieval                                │
│  • Historical Data Fetching                                     │
│  • Position Management (get, close, emergency)                  │
│  • Safety Checks:                                               │
│    - Drawdown limit                                             │
│    - Daily loss limit                                           │
│    - Consecutive losses                                         │
│    - Emergency equity threshold                                 │
│  • Weekend Close Protection                                     │
│  • New Candle Detection                                         │
│  • Main Run Loop                                                │
│  • Startup State Display                                        │
│  • Periodic Status Updates                                      │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ inherits
                ┌─────────────┴─────────────┐
                │                           │
┌───────────────▼──────────────┐  ┌────────▼──────────────────────┐
│      M5TradingBot            │  │      M1TradingBot             │
│ (live_trading_bot_           │  │ (live_trading_bot_m1_         │
│  refactored.py)              │  │  refactored.py)               │
├──────────────────────────────┤  ├───────────────────────────────┤
│  Bot-Specific (250 lines)    │  │  Bot-Specific (260 lines)     │
│                              │  │                               │
│  • Magic Number: 234000      │  │  • Magic Number: 234001       │
│  • Max Positions: 2          │  │  • Max Positions: 2           │
│  • Cooldown: 2 candles (5m)  │  │  • Cooldown: 2 candles (1m)   │
│  • Position Tracking         │  │  • Position Tracking          │
│  • Peak Profit Tracking      │  │  • Last Trade Profitability   │
└──────────────┬───────────────┘  └───────────────┬───────────────┘
               │ uses                              │ uses
               │                                   │
┌──────────────▼───────────────┐  ┌───────────────▼───────────────┐
│   M5ScalpingStrategy         │  │   M1ScalpingStrategy          │
│ (src/strategies/             │  │ (src/strategies/              │
│  m5_scalping.py)             │  │  m1_scalping.py)              │
├──────────────────────────────┤  ├───────────────────────────────┤
│  Strategy Logic (150 lines)  │  │  Strategy Logic (160 lines)   │
│                              │  │                               │
│  • Timeframe: M5 (5 min)     │  │  • Timeframe: M1 (1 min)      │
│  • Indicators:               │  │  • Indicators:                │
│    - EMA Fast: 9             │  │    - EMA Fast: 5              │
│    - EMA Slow: 21            │  │    - EMA Slow: 12             │
│    - RSI: 14 period          │  │    - RSI: 14 period           │
│    - ATR: 14 period          │  │    - ATR: 14 period           │
│  • Entry Signals:            │  │  • Entry Signals:             │
│    - LONG: RSI < 30          │  │    - LONG: RSI < 25           │
│    - SHORT: RSI > 70         │  │    - SHORT: RSI > 75          │
│  • Exit Logic:               │  │  • Exit Logic:                │
│    - Adaptive profit taking  │  │    - Signal-based adaptive    │
│    - Trend reversal exits    │  │    - Time-based fallback      │
│    - RSI threshold exits     │  │    - RSI threshold exits      │
└──────────────────────────────┘  └───────────────────────────────┘
```

## Component Responsibilities

### BaseTradingBot (Base Class)
**Purpose**: Provide shared infrastructure for all trading bots

**Responsibilities**:
- Connect/disconnect from MT5
- Fetch historical data and account information
- Manage positions (open, close, track)
- Enforce safety limits (drawdown, daily loss, consecutive losses)
- Protect against weekend gaps
- Detect new candles
- Run main trading loop
- Display startup state and periodic status

**Key Methods**:
- `connect_mt5()` / `disconnect_mt5()`
- `get_account_info()`
- `get_historical_data()`
- `get_open_positions()`
- `close_position()` / `emergency_close_all()`
- `check_drawdown()` / `check_daily_loss_limit()` / `check_consecutive_losses()`
- `is_near_weekend_close()`
- `has_new_candle()`
- `run()` - main loop

**Abstract Methods** (must be implemented by subclasses):
- `get_timeframe()` - return MT5 timeframe constant
- `compute_indicators()` - calculate technical indicators
- `trading_logic()` - main trading logic

### Strategy Classes
**Purpose**: Encapsulate strategy-specific logic

**Responsibilities**:
- Define timeframe
- Calculate technical indicators
- Generate entry signals
- Generate exit signals
- Print strategy-specific information

**Key Methods**:
- `get_timeframe()` - return MT5 timeframe constant
- `compute_indicators(df)` - calculate indicators on dataframe
- `print_indicators(latest, df, logging)` - display indicator values
- `check_entry_signal(df, current_price)` - return (signal_type, sl, tp)
- `check_exit_signal(position, df, ...)` - return (should_close, reason)

### Bot Classes (M5TradingBot, M1TradingBot)
**Purpose**: Combine base infrastructure with specific strategy

**Responsibilities**:
- Initialize with correct magic number and config
- Manage multiple positions
- Track position-specific data (open times, peak profits)
- Implement cooldown logic
- Calculate position sizes
- Place orders
- Delegate to strategy for signals

**Key Methods**:
- `__init__()` - initialize bot with strategy
- `calculate_position_size()` - determine lot size
- `place_order()` - execute trade
- `trading_logic()` - coordinate trading flow

## Data Flow

### Startup Flow
```
1. Bot.__init__()
   ├─> BaseTradingBot.__init__()
   │   ├─> load_config()
   │   └─> setup logging
   └─> Strategy.__init__()

2. Bot.run()
   ├─> connect_mt5()
   ├─> print_startup_state()
   │   ├─> get_historical_data()
   │   ├─> compute_indicators() [Strategy]
   │   └─> print_indicators() [Strategy]
   └─> main loop
```

### Trading Loop Flow
```
1. has_new_candle()
   └─> if new candle: trading_logic()

2. trading_logic()
   ├─> run_safety_checks()
   │   ├─> check_drawdown()
   │   ├─> check_daily_loss_limit()
   │   └─> check_consecutive_losses()
   │
   ├─> is_near_weekend_close()
   │   └─> if yes: close all positions
   │
   ├─> get_historical_data()
   ├─> compute_indicators() [Strategy]
   │
   ├─> Entry Logic:
   │   ├─> check cooldown
   │   ├─> check_entry_signal() [Strategy]
   │   ├─> calculate_position_size()
   │   └─> place_order()
   │
   └─> Exit Logic:
       ├─> for each position:
       │   ├─> check_exit_signal() [Strategy]
       │   └─> if should_close: close_position()
```

## Configuration Flow

```
config/m5_params.json ──┐
                        ├─> Bot.__init__()
config/m1_params.json ──┘      │
                               ├─> self.config
                               │
                               ├─> Strategy.__init__(config)
                               │   └─> self.config
                               │
                               └─> Used by:
                                   • calculate_position_size()
                                   • check_entry_signal()
                                   • check_exit_signal()
                                   • safety checks
```

## Benefits of This Architecture

### 1. Single Responsibility Principle
- **BaseTradingBot**: Infrastructure only
- **Strategy**: Trading logic only
- **Bot**: Coordination only

### 2. Don't Repeat Yourself (DRY)
- Shared code in one place (base class)
- Strategy-specific code isolated
- No duplication between bots

### 3. Open/Closed Principle
- Open for extension (new strategies)
- Closed for modification (base class stable)

### 4. Dependency Inversion
- Bots depend on abstractions (strategy interface)
- Easy to swap strategies

### 5. Testability
- Each component can be tested independently
- Mock strategies for testing infrastructure
- Mock infrastructure for testing strategies

## Adding a New Strategy

To add a new strategy (e.g., M15):

1. **Create strategy class** (`src/strategies/m15_strategy.py`):
```python
class M15Strategy:
    def __init__(self, config):
        self.config = config
    
    def get_timeframe(self):
        return mt5.TIMEFRAME_M15
    
    def compute_indicators(self, df):
        # Calculate indicators
        return df
    
    def check_entry_signal(self, df, current_price):
        # Return (signal_type, sl, tp)
        pass
    
    def check_exit_signal(self, position, df, ...):
        # Return (should_close, reason)
        pass
```

2. **Create bot class** (`live_trading_bot_m15.py`):
```python
from src.base_trading_bot import BaseTradingBot
from src.strategies.m15_strategy import M15Strategy

class M15TradingBot(BaseTradingBot):
    def __init__(self, config_path='config/m15_params.json'):
        super().__init__(config_path, magic_number=234002, strategy_name='M15')
        self.strategy = M15Strategy(self.config)
    
    def get_timeframe(self):
        return self.strategy.get_timeframe()
    
    def compute_indicators(self, df):
        return self.strategy.compute_indicators(df)
    
    def trading_logic(self):
        # Implement using strategy methods
        pass
```

3. **Create config** (`config/m15_params.json`)

4. **Test and deploy**

That's it! All infrastructure is inherited from `BaseTradingBot`.

## Comparison: Before vs After

### Before (Duplicated Code)
```
live_trading_bot.py (1051 lines)
├─ MT5 connection (50 lines)
├─ Account management (30 lines)
├─ Position management (100 lines)
├─ Safety checks (150 lines)
├─ M5 indicators (50 lines)
├─ M5 entry logic (100 lines)
├─ M5 exit logic (150 lines)
├─ Main loop (100 lines)
└─ Utilities (321 lines)

live_trading_bot_m1.py (1154 lines)
├─ MT5 connection (50 lines) ← DUPLICATE
├─ Account management (30 lines) ← DUPLICATE
├─ Position management (100 lines) ← DUPLICATE
├─ Safety checks (150 lines) ← DUPLICATE
├─ M1 indicators (50 lines)
├─ M1 entry logic (120 lines)
├─ M1 exit logic (180 lines)
├─ Main loop (100 lines) ← DUPLICATE
└─ Utilities (374 lines) ← DUPLICATE

Total: 2205 lines, ~1400 lines duplicated
```

### After (Refactored)
```
src/base_trading_bot.py (450 lines)
├─ MT5 connection (50 lines)
├─ Account management (30 lines)
├─ Position management (100 lines)
├─ Safety checks (150 lines)
├─ Main loop (100 lines)
└─ Utilities (20 lines)

src/strategies/m5_scalping.py (150 lines)
├─ M5 indicators (50 lines)
├─ M5 entry logic (50 lines)
└─ M5 exit logic (50 lines)

src/strategies/m1_scalping.py (160 lines)
├─ M1 indicators (50 lines)
├─ M1 entry logic (55 lines)
└─ M1 exit logic (55 lines)

live_trading_bot_refactored.py (250 lines)
├─ Bot initialization (50 lines)
├─ Position sizing (50 lines)
├─ Order placement (50 lines)
└─ Trading coordination (100 lines)

live_trading_bot_m1_refactored.py (260 lines)
├─ Bot initialization (50 lines)
├─ Position sizing (50 lines)
├─ Order placement (50 lines)
└─ Trading coordination (110 lines)

Total: 1270 lines, minimal duplication
Savings: 935 lines (42% reduction)
```

## Conclusion

The refactored architecture provides:
- ✅ 42% code reduction
- ✅ Eliminated ~80% of duplicated code
- ✅ Clear separation of concerns
- ✅ Easy to extend with new strategies
- ✅ Improved testability
- ✅ Better maintainability
- ✅ All original features preserved

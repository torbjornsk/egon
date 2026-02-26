# Multiple Positions Implementation

## Summary
Implemented support for 2 simultaneous positions in both M5 and M1 bots to significantly improve returns.

## Test Results (Fair Comparison on Same Dataset)

### M5 Bot
- Single Position: 30.2% monthly return
- Multiple (2): 49.6% monthly return
- **Improvement: +64.0%**

### M1 Bot
- Single Position: 46.3% monthly return
- Multiple (2): 64.1% monthly return
- **Improvement: +38.3%**

### Combined Performance
- Current (single): 76.6% monthly
- Multiple (2 each): 113.7% monthly
- **Combined Improvement: +48.4%**

## Implementation Details

### Position Size Adjustment
- Base position size (15%) is now split into 2 positions of 7.5% each
- Total risk exposure remains the same: 15% @ 25x leverage = 375% effective
- Each position: 7.5% @ 25x = 187.5% effective

### Key Changes

#### Both Bots (M5 and M1)

1. **Initialization (`__init__`)**
   - Changed `self.position` to `self.positions = []`
   - Added `self.max_positions = 2`
   - Changed `self.position_open_time` to `self.position_open_times = {}` (dict by ticket)
   - Changed `self.peak_position_profit` to `self.peak_position_profits = {}` (M5 only, dict by ticket)

2. **Configuration (`load_config`)**
   - Automatically splits position size: `base_size / max_positions`
   - Logs the split configuration

3. **Position Tracking (`get_open_positions`)**
   - Renamed from `get_open_position` (singular)
   - Returns list of all positions with bot's magic number
   - Empty list if no positions

4. **Order Placement (`place_order`)**
   - Tracks position by ticket in `position_open_times` dict
   - Tracks peak profit by ticket in `peak_position_profits` dict (M5 only)

5. **Position Closing (`close_position`)**
   - Removes ticket from tracking dicts when position closes
   - Cleans up `position_open_times[ticket]`
   - Cleans up `peak_position_profits[ticket]` (M5 only)

6. **Emergency Close (`emergency_close_all`)**
   - Uses `get_open_positions()` to get all positions
   - Closes all positions in loop

7. **Trading Logic (`trading_logic`)**
   - Gets list of open positions: `open_positions = self.get_open_positions(symbol)`
   - Weekend close: closes all positions in loop
   - Entry logic: checks `len(open_positions) < self.max_positions`
   - Initializes tracking for existing positions on bot restart
   - Exit logic: iterates through all positions to check exit signals
   - Each position tracked independently by ticket number

### M5-Specific Features
- Adaptive profit taking tracked per position using `peak_position_profits[ticket]`
- Each position has independent peak profit tracking
- Exits when profit declines 30% from peak (if peak > $100)

### M1-Specific Features
- Signal-based adaptive exits tracked per position using `position_open_times[ticket]`
- Each position has independent time tracking for adaptive exits
- Exits if trend reverses or signal fades after 3 minutes while losing

## Safety Mechanisms
All existing safety mechanisms remain active:
- Dead man's switch (consecutive losses, daily loss limit, rapid loss detection)
- Emergency equity threshold
- Weekend close protection (now closes ALL positions)
- Market gap warmup (blocks new entries, continues managing existing)
- Drawdown limits

## Deployment

### Before Restarting Bots
1. Ensure no open positions or close them manually
2. Backup current config files
3. Test in demo account first (recommended)

### To Deploy
1. Stop both bots
2. Restart M5 bot: `start_bot.bat` (or `start_bot_demo.bat` for demo)
3. Restart M1 bot: `start_bot_m1.bat` (or `start_bot_m1_demo.bat` for demo)
4. Monitor logs for proper initialization

### Expected Log Output
```
Configuration loaded: M5 Strategy
Position Size: 15.0% (split into 2 positions of 7.5% each)
Leverage: 25x
Effective Position: 187.5% per position, 375.0% total
```

## Monitoring

### Check Position Count
Logs will show:
- "Placing LONG order" when opening new position
- "EXIT SIGNAL (ticket XXXXX)" when closing specific position
- Weekend close: "Closing 2 position(s) to avoid weekend gap risk"

### Verify Behavior
- Bot should open up to 2 positions when signals appear
- Each position managed independently
- Position sizes should be ~0.04 lots each (half of previous ~0.08)
- Total exposure remains same as before

## Rollback Plan
If issues occur:
1. Stop bots
2. Restore from git: `git checkout HEAD~1 live_trading_bot.py live_trading_bot_m1.py`
3. Restart bots
4. Report issues for investigation

## Files Modified
- `live_trading_bot.py` (M5 bot)
- `live_trading_bot_m1.py` (M1 bot)

## Files Created
- `analysis/test_multiple_vs_single.py` (test script for validation)
- `MULTIPLE_POSITIONS_IMPLEMENTATION.md` (this file)

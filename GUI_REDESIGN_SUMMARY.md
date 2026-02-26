# GUI Redesign - Professional Trading Dashboard

## Overview
Complete redesign of the trading bot GUI with creative visualizations and logs moved to popup windows.

## Key Features

### 1. Popup Log Windows
- Logs are no longer embedded in the main window
- Click "📋 View Logs" button to open a dedicated log window for each bot
- Log windows are automatically opened when bots start
- Keeps main dashboard clean and focused on trading data

### 2. Enhanced Account Overview
- Large, prominent display of Balance, Equity, and Profit/Loss
- Color-coded profit display (green for profit, red for loss)
- Professional card-style layout with raised borders

### 3. Market Conditions Visualization
- **Price Display**: Large, yellow-highlighted current price
- **Trend Indicator**: Color-coded trend with arrows (↑ ↓ →)
  - Green for uptrend
  - Red for downtrend
  - Gray for sideways
- **EMA Visualization**: Canvas-based chart showing:
  - Price position (yellow dot)
  - EMA Fast (green line)
  - EMA Slow (blue line)
  - Relative positioning shows market structure at a glance
- **ATR Display**: Shows current volatility

### 4. Advanced RSI Gauge
- **Large RSI Value**: 24pt bold display
- **Visual Gauge**: Color-coded bar showing RSI position
  - Background zones: Green (oversold), Blue (neutral), Red (overbought)
  - Threshold lines showing buy/sell levels
  - White marker showing current RSI position
- **Status Label**: Clear text indication of zone

### 5. Trading Logic Display
- **Entry Signal**: Large, color-coded display
  - 🔼 LONG (green)
  - 🔽 SHORT (red)
  - ⊗ None (gray)
- **Entry Status**: Shows bot's readiness
  - ✓ Ready for entry (green)
  - ⏳ Gap warmup active (yellow)
  - ⏸ Cooldown after loss (yellow)
  - ⛔ Max positions reached (red)

### 6. Position Cards
- **Individual Cards**: Each open position gets its own card
- **Card Header**: 
  - Ticket number and type (LONG/SHORT) in color
  - Current P/L in large, color-coded text
- **Card Details**:
  - Entry price
  - Current price
  - Time held in minutes
- **Scrollable**: Container scrolls if many positions open
- **Empty State**: Shows "No open positions" when idle

### 7. Combined Portfolio Status
- Bottom status bar showing totals across both bots
- Total Equity, Total Profit, Active Positions
- Color-coded based on overall profit/loss

## Visual Design

### Color Scheme
- **Background**: Dark (#1e1e1e, #2d2d2d, #3e3e3e)
- **Text**: Light gray (#e0e0e0)
- **Accent**: Blue (#007acc)
- **Success**: Teal (#4ec9b0)
- **Error**: Coral (#f48771)
- **Warning**: Yellow (#dcdcaa)
- **Neutral**: Gray (#808080)

### Layout
- Side-by-side bot panels (M5 left, M1 right)
- Each panel contains:
  1. Controls (Start/Stop/Logs buttons + Status)
  2. Account Overview (3-column card)
  3. Market Conditions (with EMA chart)
  4. RSI Gauge (large visual display)
  5. Trading Logic (entry signal + status)
  6. Position Cards (scrollable list)
- Combined status bar at bottom

## Creative Elements

1. **EMA Chart**: Real-time visualization of price relative to moving averages
2. **RSI Gauge**: Zone-based background with animated bar
3. **Position Cards**: Professional card-based layout for each trade
4. **Status Symbols**: Unicode symbols for visual clarity (●, ○, ✓, ⏳, ⏸, ⛔, 🔼, 🔽, ⊗)
5. **Trend Arrows**: Directional arrows (↑, ↓, →) for quick trend identification
6. **Color Coding**: Consistent color language throughout
   - Green = bullish/profit/buy
   - Red = bearish/loss/sell
   - Blue = neutral/info
   - Yellow = warning/price
   - Gray = inactive/none

## Technical Improvements

1. **Popup Windows**: Separate `LogWindow` class for log management
2. **Canvas Drawing**: Custom drawing functions for EMA and RSI visualizations
3. **Position Tracking**: Enhanced parsing to extract full position details
4. **Dynamic Updates**: All visualizations update in real-time (500ms refresh)
5. **Responsive Layout**: Proper grid weights for window resizing
6. **State Management**: Extended data dictionaries with position details, entry status, etc.

## Usage

1. Start the GUI: `python bot_gui.py` or run `start_gui.bat`
2. Click "▶ Start M5" or "▶ Start M1" to launch bots
3. Log windows open automatically (or click "📋 View Logs")
4. Watch the dashboard update in real-time with:
   - Account balances
   - Market conditions
   - RSI levels
   - Entry signals
   - Open positions
5. Click "■ Stop" to terminate a bot

## Benefits

- **Cleaner Interface**: No log clutter in main window
- **Better Visualization**: Charts and gauges show data at a glance
- **Professional Look**: Card-based layout with consistent styling
- **More Information**: Position cards show detailed trade info
- **Easier Monitoring**: Color coding and symbols for quick status checks
- **Scalable**: Scrollable position list handles multiple trades
- **Flexible**: Log windows can be opened/closed independently

## Files Modified
- `bot_gui.py`: Complete rewrite with new visualization system

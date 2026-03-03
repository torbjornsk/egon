"""
Check current market signals for the M5 position
Analyze why the bot is holding vs exiting
"""

import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.append('.')
from src.mt5_connector import MT5Connector
from src.timezone_utils import mt5_to_local, calculate_hold_time, format_time_local
import MetaTrader5 as mt5

def compute_indicators(df):
    df = df.copy()
    
    # M5 EMAs
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    
    # RSI (14 period)
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def main():
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("CURRENT M5 MARKET ANALYSIS - 23:45 CANDLE")
    print("=" * 100)
    print()
    
    # Get current position
    positions = mt5.positions_get(symbol='XAUUSD')
    m5_position = None
    
    for pos in positions:
        if pos.magic == 234000:  # M5 bot
            m5_position = pos
            break
    
    if m5_position is None:
        print("No M5 position found")
        connector.disconnect()
        return
    
    # Get M5 data
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=4)
    df = connector.get_historical_data('XAUUSD', 'M5', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to get data")
        connector.disconnect()
        return
    
    df = compute_indicators(df)
    
    # Show last 10 candles
    print("LAST 10 M5 CANDLES:")
    print()
    recent = df.tail(10)
    
    for i, (idx, row) in enumerate(recent.iterrows()):
        is_current = (i == len(recent) - 1)
        marker = ">>> " if is_current else "    "
        
        print(f"{marker}{row['time']} | Price: ${row['close']:.2f} | RSI: {row['RSI']:.1f} | Trend: {'UP' if row['uptrend'] else 'DOWN'}")
        print(f"{marker}   EMA Fast: ${row['ema_fast']:.2f}, Slow: ${row['ema_slow']:.2f}")
        
        if is_current:
            print(f"{marker}   ⚠ CURRENT CANDLE (23:45 or latest)")
    
    print()
    print("=" * 100)
    print("POSITION ANALYSIS")
    print("=" * 100)
    
    latest = df.iloc[-1]
    entry_price = m5_position.price_open
    current_price = latest['close']
    current_profit = m5_position.profit
    
    # Convert MT5 timestamp to local timezone (handles DST automatically)
    time_open = mt5_to_local(m5_position.time)
    time_held, minutes_held = calculate_hold_time(time_open)
    
    print(f"Position: LONG")
    print(f"Entry: ${entry_price:.2f}")
    print(f"Current: ${current_price:.2f}")
    print(f"Profit: ${current_profit:.2f}")
    print(f"Time Held: {minutes_held:.0f} minutes")
    print()
    
    print("=" * 100)
    print("EXIT CONDITION CHECK")
    print("=" * 100)
    print()
    
    # Check each exit condition
    print("1. STANDARD RSI EXIT (RSI > 70):")
    print(f"   Current RSI: {latest['RSI']:.1f}")
    print(f"   Threshold: 70")
    print(f"   Status: {'✅ TRIGGERED' if latest['RSI'] > 70 else '❌ NOT TRIGGERED'}")
    if latest['RSI'] <= 70:
        print(f"   → Need RSI to rise {70 - latest['RSI']:.1f} more points")
    print()
    
    print("2. TAKE PROFIT (1% target):")
    tp_target = entry_price * 1.01
    print(f"   Current: ${current_price:.2f}")
    print(f"   TP Target: ${tp_target:.2f}")
    print(f"   Status: {'✅ TRIGGERED' if current_price >= tp_target else '❌ NOT TRIGGERED'}")
    if current_price < tp_target:
        distance = tp_target - current_price
        pct = (distance / current_price) * 100
        print(f"   → Need ${distance:.2f} ({pct:.2f}%) more to reach TP")
    print()
    
    print("3. ADAPTIVE: PROFIT DECLINE (30% from peak):")
    print(f"   Current Profit: ${current_profit:.2f}")
    print(f"   Minimum for trigger: $100")
    if current_profit > 100:
        print(f"   Status: Profit > $100, tracking peak")
        print(f"   → Bot is tracking peak profit")
        print(f"   → Will exit if profit drops 30% from peak")
        print(f"   → Example: If peak hits $150, will exit at $105")
    else:
        print(f"   Status: ❌ NOT TRIGGERED (profit < $100)")
        print(f"   → Need ${100 - current_profit:.2f} more profit to activate")
    print()
    
    print("4. ADAPTIVE: TREND REVERSAL (profit > $50, RSI > 60, downtrend):")
    print(f"   Current Profit: ${current_profit:.2f} (need > $50)")
    print(f"   Current RSI: {latest['RSI']:.1f} (need > 60)")
    print(f"   Current Trend: {'DOWN' if latest['downtrend'] else 'UP'} (need DOWN)")
    print(f"   Time Held: {minutes_held:.0f} min (need > 15)")
    
    conditions_met = []
    if current_profit > 50:
        conditions_met.append("✅ Profit > $50")
    else:
        conditions_met.append(f"❌ Profit ${current_profit:.2f} < $50")
    
    if latest['RSI'] > 60:
        conditions_met.append("✅ RSI > 60")
    else:
        conditions_met.append(f"❌ RSI {latest['RSI']:.1f} < 60")
    
    if latest['downtrend']:
        conditions_met.append("✅ Downtrend")
    else:
        conditions_met.append("❌ Still uptrend")
    
    if minutes_held > 15:
        conditions_met.append("✅ Held > 15 min")
    else:
        conditions_met.append(f"❌ Held {minutes_held:.0f} < 15 min")
    
    for cond in conditions_met:
        print(f"   {cond}")
    
    all_met = all("✅" in c for c in conditions_met)
    print(f"   Status: {'✅ TRIGGERED' if all_met else '❌ NOT TRIGGERED'}")
    print()
    
    print("=" * 100)
    print("MARKET SIGNAL INTERPRETATION")
    print("=" * 100)
    print()
    
    # Analyze trend
    ema_diff = latest['ema_fast'] - latest['ema_slow']
    ema_diff_pct = (ema_diff / latest['ema_slow']) * 100
    
    print(f"Trend Analysis:")
    print(f"  EMA Fast: ${latest['ema_fast']:.2f}")
    print(f"  EMA Slow: ${latest['ema_slow']:.2f}")
    print(f"  Difference: ${ema_diff:.2f} ({ema_diff_pct:+.2f}%)")
    
    if latest['uptrend']:
        if ema_diff_pct > 0.1:
            print(f"  → Strong uptrend (fast > slow by {ema_diff_pct:.2f}%)")
            print(f"  → Signal: BULLISH - price likely to continue up")
        else:
            print(f"  → Weak uptrend (fast barely above slow)")
            print(f"  → Signal: NEUTRAL - trend may be weakening")
    else:
        print(f"  → Downtrend (fast < slow)")
        print(f"  → Signal: BEARISH - price may go down")
    print()
    
    # Analyze RSI
    print(f"RSI Analysis:")
    print(f"  Current: {latest['RSI']:.1f}")
    
    if latest['RSI'] > 70:
        print(f"  → Overbought (> 70)")
        print(f"  → Signal: BEARISH - likely to reverse down")
    elif latest['RSI'] > 60:
        print(f"  → Strong (60-70)")
        print(f"  → Signal: BULLISH but approaching overbought")
    elif latest['RSI'] > 50:
        print(f"  → Neutral-Bullish (50-60)")
        print(f"  → Signal: NEUTRAL - could go either way")
    elif latest['RSI'] > 40:
        print(f"  → Neutral-Bearish (40-50)")
        print(f"  → Signal: NEUTRAL - could go either way")
    elif latest['RSI'] > 30:
        print(f"  → Weak (30-40)")
        print(f"  → Signal: BEARISH but approaching oversold")
    else:
        print(f"  → Oversold (< 30)")
        print(f"  → Signal: BULLISH - likely to reverse up")
    print()
    
    print("=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    print()
    
    if latest['RSI'] < 50 and latest['downtrend']:
        print("⚠️  BEARISH SIGNALS:")
        print(f"   - RSI {latest['RSI']:.1f} (below neutral)")
        print(f"   - Downtrend active")
        print(f"   → Price may go DOWN from here")
        print()
        print("   Bot is holding because:")
        print(f"   - Profit (${current_profit:.2f}) hasn't declined 30% from peak yet")
        print(f"   - RSI not > 60 for trend reversal exit")
        print(f"   - Standard RSI exit needs 70, currently {latest['RSI']:.1f}")
    elif latest['RSI'] > 50 and latest['uptrend']:
        print("✅ BULLISH SIGNALS:")
        print(f"   - RSI {latest['RSI']:.1f} (above neutral)")
        print(f"   - Uptrend active")
        print(f"   → Price may go UP from here")
        print()
        print("   Bot is holding because signals suggest continuation")
    else:
        print("⚠️  MIXED SIGNALS:")
        print(f"   - RSI: {latest['RSI']:.1f}")
        print(f"   - Trend: {'UP' if latest['uptrend'] else 'DOWN'}")
        print(f"   → Direction unclear, bot waiting for clearer signal")
    
    connector.disconnect()

if __name__ == "__main__":
    main()

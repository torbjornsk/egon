"""
Analyze what M5 bot missed during gap opening
Shows why trend-following would have been better
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def analyze_gap_opportunity():
    """Analyze the gap opening opportunity"""
    
    print("="*70)
    print("GAP OPENING ANALYSIS")
    print("="*70)
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get M5 data from the gap period
    # Assuming gap was around Sunday evening / Monday morning
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 200)
    
    if rates_m5 is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df_m5 = pd.DataFrame(rates_m5)
    df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
    
    # Find the gap
    print("\n1. DETECTING GAP")
    print("-" * 70)
    
    gap_found = False
    gap_index = None
    
    for i in range(1, len(df_m5)):
        time_diff = (df_m5.iloc[i]['time'] - df_m5.iloc[i-1]['time']).total_seconds() / 60
        
        if time_diff > 30:  # More than 30 minutes = likely gap
            price_before = df_m5.iloc[i-1]['close']
            price_after = df_m5.iloc[i]['open']
            gap_size = price_after - price_before
            gap_pct = (gap_size / price_before) * 100
            
            if abs(gap_pct) > 0.3:  # Significant gap
                gap_found = True
                gap_index = i
                
                print(f"Gap found at index {i}:")
                print(f"  Time before: {df_m5.iloc[i-1]['time']}")
                print(f"  Time after:  {df_m5.iloc[i]['time']}")
                print(f"  Time gap: {time_diff:.0f} minutes")
                print(f"  Price before close: ${price_before:.2f}")
                print(f"  Price after open:   ${price_after:.2f}")
                print(f"  Gap size: ${gap_size:.2f} ({gap_pct:+.2f}%)")
                print(f"  Direction: {'UP' if gap_size > 0 else 'DOWN'}")
                break
    
    if not gap_found:
        print("No significant gap found in recent data")
        mt5.shutdown()
        return
    
    # Analyze what happened after the gap
    print(f"\n2. POST-GAP PRICE ACTION")
    print("-" * 70)
    
    # Look at next 20 candles (100 minutes)
    post_gap = df_m5.iloc[gap_index:gap_index+20]
    
    if len(post_gap) > 0:
        gap_open = post_gap.iloc[0]['open']
        highest = post_gap['high'].max()
        lowest = post_gap['low'].min()
        final = post_gap.iloc[-1]['close']
        
        print(f"Next 20 candles (100 minutes) after gap:")
        print(f"  Gap open: ${gap_open:.2f}")
        print(f"  Highest:  ${highest:.2f} (+${highest-gap_open:.2f}, +{((highest-gap_open)/gap_open)*100:.2f}%)")
        print(f"  Lowest:   ${lowest:.2f} (${lowest-gap_open:.2f}, {((lowest-gap_open)/gap_open)*100:.2f}%)")
        print(f"  Final:    ${final:.2f} (${final-gap_open:.2f}, {((final-gap_open)/gap_open)*100:.2f}%)")
        
        # Calculate potential profit
        if gap_size > 0:  # Gap up
            potential_profit = highest - gap_open
            print(f"\n  If entered LONG at gap open:")
            print(f"    Best case: +${potential_profit:.2f} (+{(potential_profit/gap_open)*100:.2f}%)")
            print(f"    With 0.15 lots: ${potential_profit * 0.15 * 100:.2f} profit")
        else:  # Gap down
            potential_profit = gap_open - lowest
            print(f"\n  If entered SHORT at gap open:")
            print(f"    Best case: +${potential_profit:.2f} (+{(potential_profit/gap_open)*100:.2f}%)")
            print(f"    With 0.15 lots: ${potential_profit * 0.15 * 100:.2f} profit")
    
    # Analyze M5 bot behavior
    print(f"\n3. WHY M5 BOT MISSED IT")
    print("-" * 70)
    
    # Calculate RSI for the period
    delta = df_m5['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df_m5['RSI'] = 100 - (100 / (1 + rs))
    
    # Check RSI at gap and after
    if gap_index < len(df_m5):
        rsi_at_gap = df_m5.iloc[gap_index]['RSI']
        print(f"M5 Bot uses RSI thresholds: Buy < 30, Sell > 70")
        print(f"RSI at gap opening: {rsi_at_gap:.1f}")
        
        if gap_size > 0:  # Gap up
            if rsi_at_gap > 30:
                print(f"  ❌ RSI too high for LONG entry (needs < 30)")
                print(f"  Bot waits for oversold, but price keeps rising!")
        else:  # Gap down
            if rsi_at_gap < 70:
                print(f"  ❌ RSI too low for SHORT entry (needs > 70)")
                print(f"  Bot waits for overbought, but price keeps falling!")
        
        print(f"\nM5 bot also has:")
        print(f"  - 2 candle warmup after gaps (10 minutes)")
        print(f"  - Mean reversion strategy (expects price to reverse)")
        print(f"  - Tight RSI thresholds (misses trending moves)")
    
    # Recommendations
    print(f"\n4. RECOMMENDATIONS")
    print("-" * 70)
    print(f"For gap openings and strong trends, use:")
    print(f"")
    print(f"Option 1: Trend Bot (already built)")
    print(f"  python live_trading_bot_trend.py")
    print(f"  - Uses H1/H4 timeframes")
    print(f"  - Trend-following logic")
    print(f"  - Better for post-news moves")
    print(f"")
    print(f"Option 2: Gap Trading Strategy (new)")
    print(f"  - Detects gaps automatically")
    print(f"  - Trades in gap direction if momentum continues")
    print(f"  - Uses M15 timeframe")
    print(f"  - Wider stops and targets")
    print(f"")
    print(f"Option 3: Adjust M5 Bot")
    print(f"  - Widen RSI thresholds (e.g., 40/60)")
    print(f"  - Add trend filter")
    print(f"  - Reduce warmup period")
    print(f"  - But this makes it less effective for normal scalping")
    print(f"")
    print(f"Best approach: Run BOTH bots")
    print(f"  - M1 bot: Fast scalping in normal conditions")
    print(f"  - Trend bot: Catches big moves and trends")
    print(f"  - Different magic numbers prevent conflicts")
    
    mt5.shutdown()
    print("\n" + "="*70)

if __name__ == "__main__":
    analyze_gap_opportunity()

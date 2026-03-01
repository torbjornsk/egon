"""
Gap Trading Strategy
Capitalizes on strong moves after weekend gaps or major news
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class GapTradingStrategy:
    """Strategy for trading gaps and strong momentum moves"""
    
    def __init__(self, config):
        self.config = config
    
    def get_timeframe(self):
        """Use M5 for gap detection but M15 for trading"""
        return mt5.TIMEFRAME_M15
    
    def detect_gap(self, df):
        """Detect if there's a significant gap
        
        Returns: (has_gap, gap_size_pct, gap_direction)
        """
        if len(df) < 2:
            return False, 0, None
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Check time gap (more than 15 minutes suggests market was closed)
        time_gap_minutes = (latest['time'] - previous['time']).total_seconds() / 60
        
        if time_gap_minutes > 30:  # Likely a gap
            # Calculate price gap
            gap_size = abs(latest['open'] - previous['close'])
            gap_pct = (gap_size / previous['close']) * 100
            
            # Determine direction
            if latest['open'] > previous['close']:
                direction = 'UP'
            else:
                direction = 'DOWN'
            
            # Significant gap threshold
            min_gap_pct = self.config.get('min_gap_pct', 0.3)  # 0.3% = ~$16 on gold
            
            if gap_pct >= min_gap_pct:
                return True, gap_pct, direction
        
        return False, 0, None
    
    def compute_indicators(self, df):
        """Calculate indicators for gap trading"""
        df = df.copy()
        
        # EMAs for trend confirmation
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        
        # RSI for momentum
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR for volatility
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        
        # Momentum indicator
        df['momentum'] = df['close'] - df['close'].shift(10)
        
        # Strong trend detection
        df['strong_uptrend'] = (df['ema_9'] > df['ema_21']) & (df['ema_21'] > df['ema_50']) & (df['close'] > df['ema_9'])
        df['strong_downtrend'] = (df['ema_9'] < df['ema_21']) & (df['ema_21'] < df['ema_50']) & (df['close'] < df['ema_9'])
        
        return df
    
    def print_indicators(self, latest, df, logging):
        """Print strategy-specific indicators"""
        logging.info(f"  EMA 9: {latest['ema_9']:.2f}")
        logging.info(f"  EMA 21: {latest['ema_21']:.2f}")
        logging.info(f"  EMA 50: {latest['ema_50']:.2f}")
        logging.info(f"  RSI: {latest['RSI']:.2f}")
        logging.info(f"  ATR: {latest['ATR']:.2f}")
        logging.info(f"  Momentum: {latest['momentum']:.2f}")
        
        if latest['strong_uptrend']:
            logging.info(f"  Trend: STRONG UPTREND")
        elif latest['strong_downtrend']:
            logging.info(f"  Trend: STRONG DOWNTREND")
        else:
            logging.info(f"  Trend: WEAK/SIDEWAYS")
    
    def check_entry_signal(self, df, current_price, gap_info=None):
        """Check for entry signals
        
        Args:
            df: DataFrame with indicators
            current_price: Current market price
            gap_info: (has_gap, gap_size_pct, gap_direction) from detect_gap()
        
        Returns: (signal_type, sl, tp) where signal_type is 'LONG', 'SHORT', or None
        """
        latest = df.iloc[-1]
        
        # If we have a gap, trade in the gap direction if momentum continues
        if gap_info and gap_info[0]:  # has_gap
            gap_direction = gap_info[2]
            gap_size_pct = gap_info[1]
            
            # For gap up: Enter long if still in strong uptrend
            if gap_direction == 'UP' and latest['strong_uptrend']:
                # RSI not too overbought (allow higher than normal)
                if latest['RSI'] < 80:
                    stop_distance = latest['ATR'] * self.config.get('atr_multiplier', 2.5)
                    sl = current_price - stop_distance
                    # Wider profit target for trending moves
                    tp = current_price + (stop_distance * 2.5)  # 1:2.5 R:R
                    return 'LONG', sl, tp
            
            # For gap down: Enter short if still in strong downtrend
            elif gap_direction == 'DOWN' and latest['strong_downtrend']:
                if latest['RSI'] > 20:
                    stop_distance = latest['ATR'] * self.config.get('atr_multiplier', 2.5)
                    sl = current_price + stop_distance
                    tp = current_price - (stop_distance * 2.5)
                    return 'SHORT', sl, tp
        
        # No gap, but strong trend continuation
        else:
            # Strong uptrend entry
            if latest['strong_uptrend'] and latest['RSI'] > 50 and latest['RSI'] < 75:
                # Pullback entry: price near EMA9
                if abs(current_price - latest['ema_9']) / latest['ema_9'] < 0.002:  # Within 0.2%
                    stop_distance = latest['ATR'] * self.config.get('atr_multiplier', 2.0)
                    sl = current_price - stop_distance
                    tp = current_price + (stop_distance * 2.0)
                    return 'LONG', sl, tp
            
            # Strong downtrend entry
            elif latest['strong_downtrend'] and latest['RSI'] < 50 and latest['RSI'] > 25:
                if abs(current_price - latest['ema_9']) / latest['ema_9'] < 0.002:
                    stop_distance = latest['ATR'] * self.config.get('atr_multiplier', 2.0)
                    sl = current_price + stop_distance
                    tp = current_price - (stop_distance * 2.0)
                    return 'SHORT', sl, tp
        
        return None, None, None
    
    def check_exit_signal(self, position, df, position_open_times, logging):
        """Check if position should be closed
        
        Returns: (should_close, reason)
        """
        latest = df.iloc[-1]
        position_type = position.type
        current_profit = position.profit
        ticket = position.ticket
        
        # Time-based trailing stop
        if ticket in position_open_times:
            time_held = datetime.now() - position_open_times[ticket]
            minutes_held = time_held.total_seconds() / 60
            
            # If profitable and held for a while, use tighter trailing stop
            if current_profit > 50 and minutes_held >= 30:
                if position_type == mt5.ORDER_TYPE_BUY:
                    # Long: exit if trend weakens
                    if not latest['strong_uptrend']:
                        return True, f"Trend weakened after {minutes_held:.0f}min, profit ${current_profit:.2f}"
                    # Or if RSI shows exhaustion
                    if latest['RSI'] > 80:
                        return True, f"RSI exhaustion ({latest['RSI']:.1f}), profit ${current_profit:.2f}"
                else:
                    # Short: exit if trend weakens
                    if not latest['strong_downtrend']:
                        return True, f"Trend weakened after {minutes_held:.0f}min, profit ${current_profit:.2f}"
                    if latest['RSI'] < 20:
                        return True, f"RSI exhaustion ({latest['RSI']:.1f}), profit ${current_profit:.2f}"
        
        # Trend reversal exit
        if position_type == mt5.ORDER_TYPE_BUY:
            # Long: exit if strong downtrend forms
            if latest['strong_downtrend']:
                return True, f"Trend reversal to downtrend"
        else:
            # Short: exit if strong uptrend forms
            if latest['strong_uptrend']:
                return True, f"Trend reversal to uptrend"
        
        return False, None

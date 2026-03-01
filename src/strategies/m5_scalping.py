"""
M5 Scalping Strategy
5-minute timeframe scalping with adaptive profit taking
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

class M5ScalpingStrategy:
    """M5 scalping strategy with adaptive exits"""
    
    def __init__(self, config):
        self.config = config
    
    def get_timeframe(self):
        """Return MT5 timeframe constant"""
        return mt5.TIMEFRAME_M5
    
    def compute_indicators(self, df):
        """Calculate technical indicators for M5 strategy"""
        df = df.copy()
        
        # EMAs
        df['ema_fast'] = df['close'].ewm(span=self.config['fast_ema']).mean()
        df['ema_slow'] = df['close'].ewm(span=self.config['slow_ema']).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(self.config['rsi_period']).mean()
        loss = -delta.clip(upper=0).rolling(self.config['rsi_period']).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        
        # Trend
        df['ema_200'] = df['close'].ewm(span=200).mean()
        df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
        df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
        
        return df
    
    def print_indicators(self, latest, df, logging):
        """Print strategy-specific indicators"""
        logging.info(f"  EMA Fast ({self.config['fast_ema']}): {latest['ema_fast']:.2f}")
        logging.info(f"  EMA Slow ({self.config['slow_ema']}): {latest['ema_slow']:.2f}")
        logging.info(f"  RSI: {latest['RSI']:.2f}")
        logging.info(f"  ATR: {latest['ATR']:.2f}")
        
        trend = "UPTREND" if latest['uptrend'] else "DOWNTREND" if latest['downtrend'] else "SIDEWAYS"
        logging.info(f"  Trend: {trend}")
    
    def check_entry_signal(self, df, current_price):
        """Check for entry signals
        
        Returns: (signal_type, sl, tp) where signal_type is 'LONG', 'SHORT', or None
        """
        latest = df.iloc[-1]
        
        # LONG ENTRY
        if latest['RSI'] < self.config['rsi_buy']:
            stop_distance = latest['ATR'] * self.config['atr_multiplier']
            sl = current_price - stop_distance
            tp = current_price + (current_price * self.config['profit_target_pct'])
            return 'LONG', sl, tp
        
        # SHORT ENTRY
        elif self.config['enable_shorts'] and latest['RSI'] > self.config['rsi_sell'] and latest['downtrend']:
            stop_distance = latest['ATR'] * self.config['atr_multiplier']
            sl = current_price + stop_distance
            tp = current_price - (current_price * self.config['profit_target_pct'])
            return 'SHORT', sl, tp
        
        return None, None, None
    
    def check_exit_signal(self, position, df, position_open_times, peak_position_profits, logging):
        """Check if position should be closed
        
        Returns: (should_close, reason)
        """
        latest = df.iloc[-1]
        position_type = position.type
        current_profit = position.profit
        ticket = position.ticket
        
        # ADAPTIVE PROFIT TAKING: Lock in profits if they start declining
        if ticket in position_open_times:
            time_held = datetime.now() - position_open_times[ticket]
            minutes_held = time_held.total_seconds() / 60
            
            # Track peak profit for this position
            if ticket not in peak_position_profits:
                peak_position_profits[ticket] = current_profit
            else:
                peak_position_profits[ticket] = max(peak_position_profits[ticket], current_profit)
            
            # Adaptive profit taking: if profit > $100 and dropped 30% from peak
            if current_profit > 100 and peak_position_profits[ticket] > 100:
                profit_decline = peak_position_profits[ticket] - current_profit
                decline_pct = (profit_decline / peak_position_profits[ticket]) * 100
                
                if decline_pct > 30:
                    reason = f"Adaptive profit taking: profit declined {decline_pct:.1f}% from peak ${peak_position_profits[ticket]:.2f}"
                    logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Locking in ${current_profit:.2f} (was ${peak_position_profits[ticket]:.2f})")
                    return True, reason
            
            # Also exit if profitable and RSI shows reversal signal
            if current_profit > 50 and minutes_held >= 15:
                if position_type == mt5.ORDER_TYPE_BUY:
                    # LONG: exit if RSI > 60 and trend reversing
                    if latest['RSI'] > 60 and latest['downtrend']:
                        reason = f"Adaptive: profitable ${current_profit:.2f}, RSI {latest['RSI']:.1f}, trend reversing"
                        logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Taking profit on trend reversal")
                        return True, reason
                else:
                    # SHORT: exit if RSI < 40 and trend reversing
                    if latest['RSI'] < 40 and latest['uptrend']:
                        reason = f"Adaptive: profitable ${current_profit:.2f}, RSI {latest['RSI']:.1f}, trend reversing"
                        logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Taking profit on trend reversal")
                        return True, reason
        
        # Standard RSI exits
        if position_type == mt5.ORDER_TYPE_BUY:
            # Long position
            if latest['RSI'] > self.config['rsi_sell']:
                return True, f"RSI overbought ({latest['RSI']:.2f})"
        else:
            # Short position
            if latest['RSI'] < self.config['rsi_buy']:
                return True, f"RSI oversold ({latest['RSI']:.2f})"
        
        return False, None

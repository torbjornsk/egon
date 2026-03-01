"""
M1 Scalping Strategy
1-minute timeframe aggressive scalping with adaptive exits
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

class M1ScalpingStrategy:
    """M1 scalping strategy with signal-based adaptive exits"""
    
    def __init__(self, config):
        self.config = config
    
    def get_timeframe(self):
        """Return MT5 timeframe constant"""
        return mt5.TIMEFRAME_M1
    
    def compute_indicators(self, df):
        """Calculate technical indicators for M1 strategy"""
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
    
    def check_exit_signal(self, position, df, position_open_times, logging):
        """Check if position should be closed
        
        Returns: (should_close, reason)
        """
        latest = df.iloc[-1]
        position_type = position.type
        current_profit = position.profit
        ticket = position.ticket
        current_price = latest['close']
        
        # ADAPTIVE EXIT: Signal-based early exit for M1 scalping
        # For short-term signals, exit if signal clearly fails
        if ticket in position_open_times:
            time_held = datetime.now() - position_open_times[ticket]
            minutes_held = time_held.total_seconds() / 60
            
            # Only apply adaptive exits if losing and held for at least 3 minutes
            if current_profit < 0 and minutes_held >= 3:
                price_change = abs(current_price - position.price_open)
                is_sideways = price_change < latest['ATR'] * 0.3
                
                if position_type == mt5.ORDER_TYPE_BUY:
                    # LONG position: exit if trend reverses to downtrend while losing
                    if latest['downtrend']:
                        reason = f"Adaptive: trend reversed to downtrend while losing ${abs(current_profit):.2f} after {minutes_held:.1f} min"
                        logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Trend reversal against LONG")
                        return True, reason
                    # OR exit if signal fades (RSI > 50) and price sideways
                    elif latest['RSI'] > 50 and is_sideways:
                        reason = f"Adaptive: signal faded + sideways movement after {minutes_held:.1f} min"
                        logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Signal fading for LONG")
                        return True, reason
                
                else:
                    # SHORT position: exit if trend reverses to uptrend while losing
                    if latest['uptrend']:
                        reason = f"Adaptive: trend reversed to uptrend while losing ${abs(current_profit):.2f} after {minutes_held:.1f} min"
                        logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Trend reversal against SHORT")
                        return True, reason
                    # OR exit if signal fades (RSI < 50) and price sideways
                    elif latest['RSI'] < 50 and is_sideways:
                        reason = f"Adaptive: signal faded + sideways movement after {minutes_held:.1f} min"
                        logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Signal fading for SHORT")
                        return True, reason
            
            # Fallback: Time-based exit if still losing after 10 minutes
            if current_profit < 0 and minutes_held >= 10:
                reason = f"Adaptive: losing ${abs(current_profit):.2f} after {minutes_held:.1f} minutes"
                logging.info(f"ADAPTIVE EXIT (ticket {ticket}): Time-based fallback")
                return True, reason
        
        # Standard RSI exits
        if position_type == mt5.ORDER_TYPE_BUY:
            # LONG POSITION
            exit_threshold = self.config.get('rsi_exit_long', self.config['rsi_sell'])
            if latest['RSI'] > exit_threshold:
                return True, f"RSI exit threshold ({latest['RSI']:.2f} > {exit_threshold})"
        else:
            # SHORT POSITION
            exit_threshold = self.config.get('rsi_exit_short', self.config['rsi_buy'])
            if latest['RSI'] < exit_threshold:
                return True, f"RSI exit threshold ({latest['RSI']:.2f} < {exit_threshold})"
        
        return False, None

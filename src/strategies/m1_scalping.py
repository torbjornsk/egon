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
    
    def check_exit_signal(self, position, df, position_open_times, rsi_confirmation_tracker, logging):
        """Check if position should be closed
        
        Returns: (should_close, reason)
        """
        latest = df.iloc[-1]
        previous = df.iloc[-2] if len(df) >= 2 else latest
        position_type = position.type
        ticket = position.ticket
        
        # RSI CONFIRMATION: Require 2 consecutive candles above/below threshold
        # This prevents false exits on brief RSI spikes (100% of M1 spikes are false signals)
        use_confirmation = self.config.get('rsi_exit_confirmation', True)
        
        if position_type == mt5.ORDER_TYPE_BUY:
            # LONG POSITION
            exit_threshold = self.config.get('rsi_exit_long', self.config['rsi_sell'])
            
            if use_confirmation:
                # Check if RSI is above threshold NOW and was above threshold LAST candle
                current_above = latest['RSI'] > exit_threshold
                previous_above = previous['RSI'] > exit_threshold
                
                if current_above and previous_above:
                    return True, f"RSI exit confirmed ({latest['RSI']:.2f} > {exit_threshold} for 2 candles)"
                elif current_above:
                    # First candle above threshold - track it but don't exit yet
                    if ticket not in rsi_confirmation_tracker:
                        rsi_confirmation_tracker[ticket] = {'count': 1, 'threshold': exit_threshold}
                        logging.info(f"RSI {latest['RSI']:.2f} > {exit_threshold} - waiting for confirmation")
                    return False, None
                else:
                    # RSI dropped back below - reset tracker
                    if ticket in rsi_confirmation_tracker:
                        del rsi_confirmation_tracker[ticket]
                    return False, None
            else:
                # No confirmation - exit immediately (old behavior)
                if latest['RSI'] > exit_threshold:
                    return True, f"RSI exit threshold ({latest['RSI']:.2f} > {exit_threshold})"
                    
        else:
            # SHORT POSITION
            exit_threshold = self.config.get('rsi_exit_short', self.config['rsi_buy'])
            
            if use_confirmation:
                # Check if RSI is below threshold NOW and was below threshold LAST candle
                current_below = latest['RSI'] < exit_threshold
                previous_below = previous['RSI'] < exit_threshold
                
                if current_below and previous_below:
                    return True, f"RSI exit confirmed ({latest['RSI']:.2f} < {exit_threshold} for 2 candles)"
                elif current_below:
                    # First candle below threshold - track it but don't exit yet
                    if ticket not in rsi_confirmation_tracker:
                        rsi_confirmation_tracker[ticket] = {'count': 1, 'threshold': exit_threshold}
                        logging.info(f"RSI {latest['RSI']:.2f} < {exit_threshold} - waiting for confirmation")
                    return False, None
                else:
                    # RSI rose back above - reset tracker
                    if ticket in rsi_confirmation_tracker:
                        del rsi_confirmation_tracker[ticket]
                    return False, None
            else:
                # No confirmation - exit immediately (old behavior)
                if latest['RSI'] < exit_threshold:
                    return True, f"RSI exit threshold ({latest['RSI']:.2f} < {exit_threshold})"
        
        return False, None

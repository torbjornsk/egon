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
        from datetime import datetime
        import pytz
        
        latest = df.iloc[-1]
        position_type = position.type
        current_profit = position.profit
        ticket = position.ticket
        
        if ticket in position_open_times:
            # Get current time in the same timezone as position_open_times
            open_time = position_open_times[ticket]
            if open_time.tzinfo is not None:
                # Timezone-aware datetime
                current_time = datetime.now(open_time.tzinfo)
            else:
                # Naive datetime (fallback for old code)
                current_time = datetime.now()
            
            time_held = current_time - open_time
            minutes_held = time_held.total_seconds() / 60
            
            # Track peak profit for this position
            if ticket not in peak_position_profits:
                peak_position_profits[ticket] = current_profit
            else:
                peak_position_profits[ticket] = max(peak_position_profits[ticket], current_profit)
            
            peak = peak_position_profits[ticket]
            
            # 1. TRAILING STOP (configurable)
            if self.config.get('use_trailing_stop', False):
                activate_minutes = self.config.get('trailing_activate_minutes', 30)
                activate_profit_pct = self.config.get('trailing_activate_profit_pct', 0.3)  # 0.3% of position
                decline_pct_threshold = self.config.get('trailing_decline_pct', 40)
                
                # Calculate profit as % of position value
                position_value = position.price_open * position.volume
                profit_pct = (current_profit / position_value) * 100 if position_value > 0 else 0
                peak_profit_pct = (peak / position_value) * 100 if position_value > 0 else 0
                
                if minutes_held >= activate_minutes and peak_profit_pct > activate_profit_pct:
                    profit_decline = peak - current_profit
                    decline_pct = (profit_decline / peak) * 100 if peak > 0 else 0
                    
                    if decline_pct > decline_pct_threshold:
                        reason = f"Trailing stop: profit ${current_profit:.2f} ({profit_pct:.2f}%) declined {decline_pct:.1f}% from peak ${peak:.2f} ({peak_profit_pct:.2f}%)"
                        logging.info(f"TRAILING STOP (ticket {ticket}): Locking in profit after {minutes_held:.0f} min")
                        return True, reason
            
            # 2. SMART MAX HOLD (only force exit if profitable)
            if self.config.get('use_smart_max_hold', False):
                max_hold = self.config.get('max_hold_minutes', 60)
                min_profit_pct = self.config.get('max_hold_min_profit_pct', 0.4)  # 0.4% of position
                
                if minutes_held >= max_hold:
                    # Calculate profit as % of position value
                    position_value = position.price_open * position.volume
                    profit_pct = (current_profit / position_value) * 100 if position_value > 0 else 0
                    
                    # Only force exit if we're profitable above threshold
                    if profit_pct > min_profit_pct:
                        reason = f"Smart max hold: {minutes_held:.0f} min with profit ${current_profit:.2f} ({profit_pct:.2f}%)"
                        logging.info(f"SMART MAX HOLD (ticket {ticket}): Taking profit after long hold")
                        return True, reason
                    # If losing, let it ride - might recover
                    # If small profit, let it ride - might grow
            
            # 3. TIGHTER RSI EXITS (after some time)
            tighter_rsi_minutes = self.config.get('tighter_rsi_after_minutes', 20)
            if minutes_held >= tighter_rsi_minutes:
                if position_type == mt5.ORDER_TYPE_BUY:
                    tighter_threshold = self.config.get('rsi_exit_long', self.config['rsi_sell'])
                    if latest['RSI'] > tighter_threshold:
                        reason = f"Tighter RSI exit after {minutes_held:.0f} min: {latest['RSI']:.2f} > {tighter_threshold}"
                        return True, reason
                else:
                    tighter_threshold = self.config.get('rsi_exit_short', self.config['rsi_buy'])
                    if latest['RSI'] < tighter_threshold:
                        reason = f"Tighter RSI exit after {minutes_held:.0f} min: {latest['RSI']:.2f} < {tighter_threshold}"
                        return True, reason
        
        # 4. STANDARD RSI EXITS (always active)
        if position_type == mt5.ORDER_TYPE_BUY:
            # Long position - use rsi_sell as fallback if rsi_exit_long not set
            exit_threshold = self.config.get('rsi_exit_long', self.config['rsi_sell'])
            if latest['RSI'] > exit_threshold:
                return True, f"RSI exit ({latest['RSI']:.2f} > {exit_threshold})"
        else:
            # Short position - use rsi_buy as fallback if rsi_exit_short not set
            exit_threshold = self.config.get('rsi_exit_short', self.config['rsi_buy'])
            if latest['RSI'] < exit_threshold:
                return True, f"RSI exit ({latest['RSI']:.2f} < {exit_threshold})"
        
        return False, None

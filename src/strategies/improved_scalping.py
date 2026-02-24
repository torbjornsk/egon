import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy

class ImprovedScalpingStrategy(BaseStrategy):
    """
    Improved scalping strategy combining:
    - RSI oversold/overbought for entries/exits
    - EMA trend filter
    - Multiple exit conditions (profit target, stop loss, trend reversal)
    - ATR for dynamic stop loss
    """
    
    def calculate_indicators(self, data):
        df = data.copy()
        
        # EMA for trend
        df['ema'] = df['close'].ewm(span=self.params.get('ema_period', 50), adjust=False).mean()
        
        # RSI
        rsi_period = self.params.get('rsi_period', 10)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR for dynamic stops
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(self.params.get('atr_period', 14)).mean()
        
        # Price momentum
        df['momentum'] = df['close'].pct_change(periods=5) * 100
        
        return df
    
    def generate_signals(self, data):
        df = self.calculate_indicators(data)
        
        # Initialize signal columns
        df['signal'] = 0
        df['exit_reason'] = ''
        
        # Entry parameters
        rsi_oversold = self.params.get('rsi_oversold', 30)
        rsi_overbought = self.params.get('rsi_overbought', 70)
        require_trend = self.params.get('require_uptrend', True)
        
        # Exit parameters
        profit_target_pct = self.params.get('profit_target_pct', 0.03)  # 3%
        stop_loss_pct = self.params.get('stop_loss_pct', 0.02)  # 2%
        use_atr_stops = self.params.get('use_atr_stops', True)
        atr_multiplier = self.params.get('atr_multiplier', 2.0)
        
        # BUY SIGNAL: RSI oversold + optional trend filter
        buy_condition = (df['rsi'] < rsi_oversold)
        
        if require_trend:
            # Only buy if price is above EMA (uptrend) or recently bounced
            buy_condition = buy_condition & (
                (df['close'] > df['ema']) | 
                (df['momentum'] > 0)  # Or has positive momentum
            )
        
        df.loc[buy_condition, 'signal'] = 1
        
        # SELL SIGNAL: RSI overbought (for exit)
        sell_condition = (df['rsi'] > rsi_overbought)
        df.loc[sell_condition, 'signal'] = -1
        df.loc[sell_condition, 'exit_reason'] = 'rsi_overbought'
        
        # Calculate stop loss and take profit levels
        if use_atr_stops:
            df['sl_distance'] = df['atr'] * atr_multiplier
            df['tp_distance'] = df['atr'] * atr_multiplier * 2  # 2:1 reward/risk
        else:
            df['sl_distance'] = df['close'] * stop_loss_pct
            df['tp_distance'] = df['close'] * profit_target_pct
        
        # Add trend break exit signal
        df['trend_break'] = (df['close'] < df['ema']) & (df['close'].shift(1) >= df['ema'].shift(1))
        
        return df
    
    def should_exit(self, entry_price, current_price, current_bar, position_type='long'):
        """
        Check if position should be exited based on multiple conditions
        Returns: (should_exit, reason)
        """
        if position_type == 'long':
            pct_change = (current_price - entry_price) / entry_price
            
            # Profit target hit
            if pct_change >= self.params.get('profit_target_pct', 0.03):
                return True, 'profit_target'
            
            # RSI overbought
            if current_bar['rsi'] > self.params.get('rsi_overbought', 70):
                return True, 'rsi_overbought'
            
            # Stop loss + trend break
            if pct_change <= -self.params.get('stop_loss_pct', 0.02):
                if current_bar['close'] < current_bar['ema']:
                    return True, 'stop_loss_trend_break'
            
            # Hard stop loss (ATR based)
            if 'sl_distance' in current_bar:
                if current_price <= entry_price - current_bar['sl_distance']:
                    return True, 'hard_stop_loss'
        
        return False, None

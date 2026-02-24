import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy

class ScalpingStrategy(BaseStrategy):
    def calculate_indicators(self, data):
        df = data.copy()
        
        # EMAs
        df['ema_fast'] = df['close'].ewm(span=self.params['fast_ema'], adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.params['slow_ema'], adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['rsi_period']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(self.params['atr_period']).mean()
        
        return df
    
    def generate_signals(self, data):
        df = self.calculate_indicators(data)
        
        # Initialize signal column
        df['signal'] = 0
        
        # Buy signal: Fast EMA crosses above Slow EMA and RSI < 70
        buy_condition = (
            (df['ema_fast'] > df['ema_slow']) &
            (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1)) &
            (df['rsi'] < self.params['rsi_overbought'])
        )
        
        # Sell signal: Fast EMA crosses below Slow EMA and RSI > 30
        sell_condition = (
            (df['ema_fast'] < df['ema_slow']) &
            (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1)) &
            (df['rsi'] > self.params['rsi_oversold'])
        )
        
        df.loc[buy_condition, 'signal'] = 1
        df.loc[sell_condition, 'signal'] = -1
        
        # Calculate stop loss and take profit levels
        df['sl_distance'] = df['atr'] * self.params['atr_multiplier']
        df['tp_distance'] = df['sl_distance'] * (self.params['take_profit_pips'] / self.params['stop_loss_pips'])
        
        return df

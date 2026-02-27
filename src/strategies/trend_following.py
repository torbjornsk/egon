"""
Trend Following Strategy for Gold (XAUUSD)
Multi-timeframe analysis with trailing stops
"""

import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from .base_strategy import BaseStrategy

class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following strategy using multi-timeframe analysis:
    - H4 for trend direction (EMA crossover, ADX)
    - H1 for entry timing (pullback to EMA, RSI, MACD)
    - Trailing stop loss to lock in profits
    """
    
    def __init__(self, params):
        super().__init__(params)
        self.position_entry_prices = {}  # Track entry prices for trailing stops
        self.trailing_stops = {}  # Track trailing stop levels
        
    def calculate_indicators(self, data, timeframe='H1'):
        """Calculate technical indicators for given timeframe"""
        df = data.copy()
        
        # EMAs
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR for stop loss
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()
        
        # ADX for trend strength
        df = self._calculate_adx(df)
        
        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        return df
    
    def _calculate_adx(self, df, period=14):
        """Calculate Average Directional Index (ADX)"""
        # Calculate +DM and -DM
        high_diff = df['high'].diff()
        low_diff = -df['low'].diff()
        
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        
        # Smooth with Wilder's smoothing
        atr = df['atr']
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        # Calculate DX and ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.rolling(period).mean()
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        
        return df
    
    def get_h4_trend(self, symbol='XAUUSD'):
        """Get H4 trend direction
        
        Returns:
            str: 'UPTREND', 'DOWNTREND', or 'NO_TREND'
        """
        # Get H4 data
        h4_data = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 250)
        if h4_data is None or len(h4_data) == 0:
            return 'NO_TREND'
        
        df = pd.DataFrame(h4_data)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = self.calculate_indicators(df, 'H4')
        
        # Check last candle
        last = df.iloc[-1]
        
        # Trend criteria
        ema_uptrend = last['ema_50'] > last['ema_200']
        ema_downtrend = last['ema_50'] < last['ema_200']
        strong_trend = last['adx'] > self.params.get('adx_threshold', 25)
        
        if ema_uptrend and strong_trend:
            return 'UPTREND'
        elif ema_downtrend and strong_trend:
            return 'DOWNTREND'
        else:
            return 'NO_TREND'
    
    def generate_signals(self, data, h4_trend=None):
        """Generate trading signals based on H1 data and H4 trend
        
        Args:
            data: H1 DataFrame
            h4_trend: Optional H4 trend ('UPTREND', 'DOWNTREND', 'NO_TREND')
        
        Returns:
            DataFrame with signals
        """
        df = self.calculate_indicators(data, 'H1')
        
        # Get H4 trend if not provided
        if h4_trend is None:
            h4_trend = self.get_h4_trend()
        
        # Initialize signal column
        df['signal'] = 0
        df['h4_trend'] = h4_trend
        
        # Only trade in direction of H4 trend
        if h4_trend == 'NO_TREND':
            return df
        
        # Entry conditions for LONG (in uptrend)
        if h4_trend == 'UPTREND':
            # Pullback to EMA 20
            pullback = df['close'] <= df['ema_20'] * 1.002  # Within 0.2% of EMA
            
            # RSI not overbought (40-60 range)
            rsi_ok = (df['rsi'] >= self.params.get('rsi_min', 40)) & \
                     (df['rsi'] <= self.params.get('rsi_max', 60))
            
            # MACD turning positive
            macd_bullish = (df['macd_hist'] > 0) & (df['macd_hist'].shift(1) <= 0)
            
            # Price above EMA 50 (overall uptrend on H1 too)
            h1_uptrend = df['close'] > df['ema_50']
            
            long_signal = pullback & rsi_ok & macd_bullish & h1_uptrend
            df.loc[long_signal, 'signal'] = 1
        
        # Entry conditions for SHORT (in downtrend)
        elif h4_trend == 'DOWNTREND':
            # Pullback to EMA 20
            pullback = df['close'] >= df['ema_20'] * 0.998  # Within 0.2% of EMA
            
            # RSI not oversold (40-60 range)
            rsi_ok = (df['rsi'] >= self.params.get('rsi_min', 40)) & \
                     (df['rsi'] <= self.params.get('rsi_max', 60))
            
            # MACD turning negative
            macd_bearish = (df['macd_hist'] < 0) & (df['macd_hist'].shift(1) >= 0)
            
            # Price below EMA 50 (overall downtrend on H1 too)
            h1_downtrend = df['close'] < df['ema_50']
            
            short_signal = pullback & rsi_ok & macd_bearish & h1_downtrend
            df.loc[short_signal, 'signal'] = -1
        
        # Calculate stop loss and take profit
        df['sl_distance'] = df['atr'] * self.params.get('atr_multiplier', 2.0)
        df['tp_distance'] = df['close'] * self.params.get('profit_target_pct', 0.05)
        
        return df
    
    def check_exit_signals(self, position, current_data):
        """Check if position should be exited
        
        Args:
            position: MT5 position object
            current_data: Current H1 DataFrame with indicators
            
        Returns:
            tuple: (should_exit: bool, reason: str)
        """
        if len(current_data) == 0:
            return False, None
        
        last = current_data.iloc[-1]
        current_price = last['close']
        
        # Get position details
        ticket = position.ticket
        position_type = position.type  # 0=BUY, 1=SELL
        entry_price = position.price_open
        
        # Initialize trailing stop if not exists
        if ticket not in self.trailing_stops:
            atr = last['atr']
            initial_sl_distance = atr * self.params.get('atr_multiplier', 2.0)
            
            if position_type == 0:  # BUY
                self.trailing_stops[ticket] = entry_price - initial_sl_distance
            else:  # SELL
                self.trailing_stops[ticket] = entry_price + initial_sl_distance
        
        # Update trailing stop
        trailing_stop = self._update_trailing_stop(
            ticket, position_type, entry_price, current_price, last['atr']
        )
        
        # Check trailing stop hit
        if position_type == 0:  # BUY
            if current_price <= trailing_stop:
                return True, f"Trailing stop hit at {trailing_stop:.2f}"
        else:  # SELL
            if current_price >= trailing_stop:
                return True, f"Trailing stop hit at {trailing_stop:.2f}"
        
        # Check trend reversal on H4
        h4_trend = self.get_h4_trend()
        if position_type == 0 and h4_trend == 'DOWNTREND':
            return True, "H4 trend reversed to downtrend"
        elif position_type == 1 and h4_trend == 'UPTREND':
            return True, "H4 trend reversed to uptrend"
        
        # Check RSI divergence (momentum weakening)
        if self._check_rsi_divergence(current_data, position_type):
            return True, "RSI divergence detected"
        
        # Time-based exit (max hold time)
        max_hold_hours = self.params.get('max_hold_hours', 168)  # 7 days default
        position_age_hours = (pd.Timestamp.now() - pd.to_datetime(position.time, unit='s')).total_seconds() / 3600
        if position_age_hours > max_hold_hours:
            return True, f"Max hold time reached ({max_hold_hours}h)"
        
        return False, None
    
    def _update_trailing_stop(self, ticket, position_type, entry_price, current_price, atr):
        """Update trailing stop level
        
        Trailing stop moves up (for longs) or down (for shorts) as price moves favorably,
        but never moves against the position.
        """
        current_stop = self.trailing_stops[ticket]
        trail_distance = atr * self.params.get('atr_multiplier', 2.0)
        
        if position_type == 0:  # BUY
            # Calculate profit percentage
            profit_pct = (current_price - entry_price) / entry_price
            
            # Lock in 50% of profit once we hit 5% gain
            if profit_pct >= 0.05:
                min_profit_lock = entry_price + (current_price - entry_price) * 0.5
                new_stop = max(current_stop, current_price - trail_distance, min_profit_lock)
            else:
                new_stop = max(current_stop, current_price - trail_distance)
            
            self.trailing_stops[ticket] = new_stop
            return new_stop
        
        else:  # SELL
            # Calculate profit percentage
            profit_pct = (entry_price - current_price) / entry_price
            
            # Lock in 50% of profit once we hit 5% gain
            if profit_pct >= 0.05:
                min_profit_lock = entry_price - (entry_price - current_price) * 0.5
                new_stop = min(current_stop, current_price + trail_distance, min_profit_lock)
            else:
                new_stop = min(current_stop, current_price + trail_distance)
            
            self.trailing_stops[ticket] = new_stop
            return new_stop
    
    def _check_rsi_divergence(self, data, position_type):
        """Check for RSI divergence (price makes new high/low but RSI doesn't)"""
        if len(data) < 20:
            return False
        
        recent = data.tail(20)
        
        if position_type == 0:  # BUY - check for bearish divergence
            # Price making higher highs
            price_higher = recent['close'].iloc[-1] > recent['close'].iloc[-10]
            # RSI making lower highs
            rsi_lower = recent['rsi'].iloc[-1] < recent['rsi'].iloc[-10]
            return price_higher and rsi_lower
        
        else:  # SELL - check for bullish divergence
            # Price making lower lows
            price_lower = recent['close'].iloc[-1] < recent['close'].iloc[-10]
            # RSI making higher lows
            rsi_higher = recent['rsi'].iloc[-1] > recent['rsi'].iloc[-10]
            return price_lower and rsi_higher
    
    def cleanup_position(self, ticket):
        """Clean up tracking data when position is closed"""
        if ticket in self.trailing_stops:
            del self.trailing_stops[ticket]
        if ticket in self.position_entry_prices:
            del self.position_entry_prices[ticket]

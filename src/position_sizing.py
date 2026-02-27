"""
Dynamic Position Sizing Module
Implements volatility-adjusted position sizing for improved risk-adjusted returns
"""
import MetaTrader5 as mt5
import numpy as np
from collections import deque

class VolatilityAdjustedSizing:
    """
    Adjusts position size based on recent market volatility (ATR)
    - Reduces size during high volatility (risk protection)
    - Increases size during low volatility (profit optimization)
    """
    
    def __init__(self, base_position_pct=0.075, lookback_periods=100, 
                 high_vol_multiplier=0.6, low_vol_multiplier=1.3):
        """
        Initialize volatility-adjusted sizing
        
        Args:
            base_position_pct: Base position size as % of account (e.g., 0.075 = 7.5%)
            lookback_periods: Number of candles to use for volatility calculation
            high_vol_multiplier: Multiplier when volatility is high (e.g., 0.6 = 60% of base)
            low_vol_multiplier: Multiplier when volatility is low (e.g., 1.3 = 130% of base)
        """
        self.base_position_pct = base_position_pct
        self.lookback_periods = lookback_periods
        self.high_vol_multiplier = high_vol_multiplier
        self.low_vol_multiplier = low_vol_multiplier
        
        # Store recent ATR values
        self.atr_history = deque(maxlen=lookback_periods)
    
    def update_atr(self, current_atr):
        """Update ATR history with new value"""
        self.atr_history.append(current_atr)
    
    def get_position_size(self, current_atr):
        """
        Calculate adjusted position size based on current volatility
        
        Args:
            current_atr: Current ATR value
            
        Returns:
            Adjusted position size as % of account
        """
        # Update history
        self.update_atr(current_atr)
        
        # Need enough history to calculate percentile
        if len(self.atr_history) < 20:
            return self.base_position_pct
        
        # Calculate median ATR (50th percentile)
        atr_median = np.median(list(self.atr_history))
        
        # Determine volatility regime
        if current_atr > atr_median * 1.5:
            # High volatility: reduce position size
            multiplier = self.high_vol_multiplier
            regime = "HIGH"
        elif current_atr < atr_median * 0.7:
            # Low volatility: increase position size
            multiplier = self.low_vol_multiplier
            regime = "LOW"
        else:
            # Normal volatility: use base size
            multiplier = 1.0
            regime = "NORMAL"
        
        adjusted_size = self.base_position_pct * multiplier
        
        return adjusted_size, regime
    
    def get_position_size_mt5(self, symbol, timeframe, periods=None):
        """
        Calculate position size using live MT5 data
        
        Args:
            symbol: Trading symbol (e.g., 'XAUUSD')
            timeframe: MT5 timeframe constant (e.g., mt5.TIMEFRAME_M5)
            periods: Number of periods to fetch (default: lookback_periods + 20)
            
        Returns:
            Tuple of (adjusted_size, regime, current_atr)
        """
        if periods is None:
            periods = self.lookback_periods + 20
        
        # Fetch recent candles
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, periods)
        
        if rates is None or len(rates) < 20:
            return self.base_position_pct, "UNKNOWN", 0
        
        # Calculate ATR for recent candles
        high = np.array([r['high'] for r in rates])
        low = np.array([r['low'] for r in rates])
        close = np.array([r['close'] for r in rates])
        
        # True Range
        high_low = high - low
        high_close = np.abs(high - np.roll(close, 1))
        low_close = np.abs(low - np.roll(close, 1))
        
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        
        # ATR (14-period)
        atr_period = 14
        atr_values = []
        for i in range(atr_period, len(tr)):
            atr = np.mean(tr[i-atr_period:i])
            atr_values.append(atr)
        
        if len(atr_values) == 0:
            return self.base_position_pct, "UNKNOWN", 0
        
        # Update history with recent ATR values
        for atr in atr_values[:-1]:
            self.update_atr(atr)
        
        # Get current ATR
        current_atr = atr_values[-1]
        
        # Calculate adjusted size
        adjusted_size, regime = self.get_position_size(current_atr)
        
        return adjusted_size, regime, current_atr


class PositionSizeCalculator:
    """
    Main position size calculator with multiple strategies
    """
    
    def __init__(self, strategy='volatility', **kwargs):
        """
        Initialize position size calculator
        
        Args:
            strategy: Sizing strategy ('fixed', 'volatility', 'kelly', 'equity_curve')
            **kwargs: Strategy-specific parameters
        """
        self.strategy = strategy
        
        if strategy == 'volatility':
            self.sizer = VolatilityAdjustedSizing(**kwargs)
        else:
            self.base_position_pct = kwargs.get('base_position_pct', 0.075)
    
    def calculate_lot_size(self, symbol, account_balance, position_size_pct, leverage=25):
        """
        Convert position size % to actual lot size for MT5
        
        Args:
            symbol: Trading symbol
            account_balance: Current account balance
            position_size_pct: Position size as % of account (e.g., 0.075 = 7.5%)
            leverage: Account leverage
            
        Returns:
            Lot size for MT5 order
        """
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 0.01  # Minimum lot size
        
        # Calculate position value
        position_value = account_balance * position_size_pct * leverage
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return 0.01
        
        current_price = tick.ask
        
        # Calculate lot size
        # For gold: 1 lot = 100 oz
        contract_size = symbol_info.trade_contract_size
        lot_size = position_value / (current_price * contract_size)
        
        # Round to symbol's volume step
        volume_step = symbol_info.volume_step
        lot_size = round(lot_size / volume_step) * volume_step
        
        # Ensure within min/max limits
        lot_size = max(symbol_info.volume_min, min(lot_size, symbol_info.volume_max))
        
        return lot_size
    
    def get_position_size_for_trade(self, symbol, timeframe, account_balance, 
                                    base_position_pct=0.075, leverage=25):
        """
        Get adjusted position size and lot size for a new trade
        
        Args:
            symbol: Trading symbol
            timeframe: MT5 timeframe
            account_balance: Current account balance
            base_position_pct: Base position size %
            leverage: Account leverage
            
        Returns:
            Tuple of (lot_size, position_pct, regime, info_dict)
        """
        if self.strategy == 'volatility':
            adjusted_pct, regime, current_atr = self.sizer.get_position_size_mt5(
                symbol, timeframe
            )
        else:
            adjusted_pct = base_position_pct
            regime = "FIXED"
            current_atr = 0
        
        # Calculate lot size
        lot_size = self.calculate_lot_size(symbol, account_balance, adjusted_pct, leverage)
        
        info = {
            'strategy': self.strategy,
            'base_position_pct': base_position_pct,
            'adjusted_position_pct': adjusted_pct,
            'regime': regime,
            'current_atr': current_atr,
            'lot_size': lot_size,
            'account_balance': account_balance
        }
        
        return lot_size, adjusted_pct, regime, info


# Example usage functions
def example_usage():
    """Example of how to use the position sizing module"""
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    # Create position size calculator with volatility adjustment
    calculator = PositionSizeCalculator(
        strategy='volatility',
        base_position_pct=0.075,  # 7.5% base position
        lookback_periods=100,
        high_vol_multiplier=0.6,   # 60% size in high volatility
        low_vol_multiplier=1.3     # 130% size in low volatility
    )
    
    # Get account info
    account_info = mt5.account_info()
    if account_info is None:
        print("Failed to get account info")
        mt5.shutdown()
        return
    
    account_balance = account_info.balance
    
    # Calculate position size for M5 trade
    lot_size, position_pct, regime, info = calculator.get_position_size_for_trade(
        symbol='XAUUSD',
        timeframe=mt5.TIMEFRAME_M5,
        account_balance=account_balance,
        base_position_pct=0.075,
        leverage=25
    )
    
    print(f"Position Sizing Info:")
    print(f"  Volatility Regime: {regime}")
    print(f"  Base Position: {info['base_position_pct']*100:.2f}%")
    print(f"  Adjusted Position: {info['adjusted_position_pct']*100:.2f}%")
    print(f"  Lot Size: {lot_size:.2f}")
    print(f"  Current ATR: {info['current_atr']:.2f}")
    
    mt5.shutdown()


if __name__ == '__main__':
    example_usage()

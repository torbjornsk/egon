"""
Statistically Sampled Test Suite
Uses stratified sampling to reduce computation while maintaining accuracy
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import pickle
import os
from pathlib import Path
import hashlib

class SampledTestSuite:
    def __init__(self, cache_dir='tests/data_cache', sample_ratio=0.15):
        """
        Initialize sampled test suite
        
        Args:
            cache_dir: Directory for cached data
            sample_ratio: Fraction of data to sample (0.15 = 15% of data)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sample_ratio = sample_ratio
        
        # Define test periods
        self.test_periods = {
            'recent_30d': {'days': 30, 'description': 'Last 30 days'},
            'recent_60d': {'days': 60, 'description': 'Last 60 days'},
            'recent_90d': {'days': 90, 'description': 'Last 90 days'},
            'recent_120d': {'days': 120, 'description': 'Last 120 days'},
            'full_history': {'days': 250, 'description': 'Full available history'}
        }
    
    def _get_cache_key(self, symbol, timeframe, days):
        """Generate cache key for data"""
        today = datetime.now().date()
        key_str = f"{symbol}_{timeframe}_{days}_{today}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _load_cached_data(self, cache_key):
        """Load data from cache"""
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        return None
    
    def _identify_market_regimes(self, df):
        """
        Identify different market regimes for stratified sampling
        Returns regime labels for each candle
        """
        # Compute volatility (ATR percentile)
        atr_median = df['ATR'].median()
        high_volatility = df['ATR'] > atr_median
        
        # Compute trend strength (EMA divergence)
        ema_diff = abs(df['ema_fast'] - df['ema_slow']) / df['close']
        trend_median = ema_diff.median()
        strong_trend = ema_diff > trend_median
        
        # Create regime labels
        regimes = []
        for i in range(len(df)):
            if high_volatility.iloc[i] and strong_trend.iloc[i]:
                regimes.append('high_vol_trending')
            elif high_volatility.iloc[i] and not strong_trend.iloc[i]:
                regimes.append('high_vol_ranging')
            elif not high_volatility.iloc[i] and strong_trend.iloc[i]:
                regimes.append('low_vol_trending')
            else:
                regimes.append('low_vol_ranging')
        
        df['regime'] = regimes
        return df
    
    def _stratified_sample(self, df, sample_ratio):
        """
        Perform stratified sampling based on market regimes
        Ensures proportional representation of all market conditions
        """
        # Identify regimes
        df = self._identify_market_regimes(df)
        
        # Sample from each regime proportionally
        sampled_dfs = []
        for regime in df['regime'].unique():
            regime_df = df[df['regime'] == regime]
            n_samples = max(int(len(regime_df) * sample_ratio), 1)
            
            # Use systematic sampling (every Nth row) to maintain temporal structure
            step = max(len(regime_df) // n_samples, 1)
            sampled = regime_df.iloc[::step]
            sampled_dfs.append(sampled)
        
        # Combine and sort by time
        sampled_df = pd.concat(sampled_dfs).sort_values('time').reset_index(drop=True)
        
        return sampled_df
    
    def compute_indicators(self, df, fast_ema, slow_ema, rsi_period):
        """Compute technical indicators"""
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=fast_ema, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=slow_ema, adjust=False).mean()
        df['uptrend'] = df['ema_fast'] > df['ema_slow']
        df['downtrend'] = df['ema_fast'] < df['ema_slow']
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['ATR'] = df['tr'].rolling(window=14).mean()
        
        return df
    
    def simulate_strategy(self, df, config, max_positions=2):
        """Simulate trading strategy"""
        positions = []
        closed_trades = []
        
        position_size = 0.15 / max_positions
        leverage = 25
        
        for idx in range(len(df)):
            row = df.iloc[idx]
            
            # Check exits
            for pos in positions[:]:
                exit_signal = False
                exit_reason = None
                exit_price = None
                
                if pos['type'] == 'LONG':
                    if row['close'] >= pos['tp']:
                        exit_signal, exit_reason, exit_price = True, 'TP', pos['tp']
                    elif row['close'] <= pos['sl']:
                        exit_signal, exit_reason, exit_price = True, 'SL', pos['sl']
                    elif row['RSI'] >= config['rsi_exit_long']:
                        exit_signal, exit_reason, exit_price = True, 'RSI_EXIT', row['close']
                else:  # SHORT
                    if row['close'] <= pos['tp']:
                        exit_signal, exit_reason, exit_price = True, 'TP', pos['tp']
                    elif row['close'] >= pos['sl']:
                        exit_signal, exit_reason, exit_price = True, 'SL', pos['sl']
                    elif row['RSI'] <= config['rsi_exit_short']:
                        exit_signal, exit_reason, exit_price = True, 'RSI_EXIT', row['close']
                
                if exit_signal:
                    if pos['type'] == 'LONG':
                        pnl_pct = (exit_price - pos['entry']) / pos['entry']
                    else:
                        pnl_pct = (pos['entry'] - exit_price) / pos['entry']
                    
                    profit_pct = pnl_pct * leverage * position_size
                    
                    closed_trades.append({
                        'profit_pct': profit_pct,
                        'exit_reason': exit_reason
                    })
                    positions.remove(pos)
            
            # Check entries
            if len(positions) < max_positions:
                if row['RSI'] < config['rsi_buy'] and row['uptrend']:
                    positions.append({
                        'type': 'LONG',
                        'entry': row['close'],
                        'entry_idx': idx,
                        'sl': row['close'] - (row['ATR'] * config['atr_multiplier']),
                        'tp': row['close'] * (1 + config['profit_target_pct'])
                    })
                elif config.get('enable_shorts', True) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                    positions.append({
                        'type': 'SHORT',
                        'entry': row['close'],
                        'entry_idx': idx,
                        'sl': row['close'] + (row['ATR'] * config['atr_multiplier']),
                        'tp': row['close'] * (1 - config['profit_target_pct'])
                    })
        
        return closed_trades
    
    def analyze_results(self, trades):
        """Analyze trading results"""
        if len(trades) == 0:
            return None
        
        df = pd.DataFrame(trades)
        winning = df[df['profit_pct'] > 0]
        losing = df[df['profit_pct'] <= 0]
        
        total_return = df['profit_pct'].sum()
        win_rate = len(winning) / len(trades) * 100
        
        avg_win = winning['profit_pct'].mean() if len(winning) > 0 else 0
        avg_loss = losing['profit_pct'].mean() if len(losing) > 0 else 0
        
        gross_profit = winning['profit_pct'].sum() if len(winning) > 0 else 0
        gross_loss = abs(losing['profit_pct'].sum()) if len(losing) > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        cumulative = df['profit_pct'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max)
        max_drawdown = drawdown.min()
        
        if len(trades) > 1:
            returns_std = df['profit_pct'].std()
            sharpe = (df['profit_pct'].mean() / returns_std * np.sqrt(252)) if returns_std > 0 else 0
        else:
            sharpe = 0
        
        return {
            'total_trades': len(trades),
            'win_rate': win_rate,
            'total_return': total_return * 100,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown * 100,
            'sharpe': sharpe
        }
    
    def validate_sampling(self, config, timeframe='M5'):
        """
        Validate that sampling produces statistically similar results to full data
        Returns comparison metrics
        """
        print("="*80)
        print("VALIDATING SAMPLING ACCURACY")
        print("="*80)
        
        validation_results = {}
        
        for period_name in self.test_periods.keys():
            cache_key = self._get_cache_key('XAUUSD', timeframe, self.test_periods[period_name]['days'])
            df_full = self._load_cached_data(cache_key)
            
            if df_full is None:
                continue
            
            # Test on full data
            df_full = self.compute_indicators(df_full, config['fast_ema'], config['slow_ema'], config['rsi_period'])
            trades_full = self.simulate_strategy(df_full, config)
            metrics_full = self.analyze_results(trades_full)
            
            if not metrics_full:
                continue
            
            # Test on sampled data
            df_sampled = self._stratified_sample(df_full, self.sample_ratio)
            trades_sampled = self.simulate_strategy(df_sampled, config)
            metrics_sampled = self.analyze_results(trades_sampled)
            
            if not metrics_sampled:
                continue
            
            # Calculate differences
            return_diff = abs(metrics_full['total_return'] - metrics_sampled['total_return'])
            wr_diff = abs(metrics_full['win_rate'] - metrics_sampled['win_rate'])
            pf_diff = abs(metrics_full['profit_factor'] - metrics_sampled['profit_factor'])
            
            validation_results[period_name] = {
                'full': metrics_full,
                'sampled': metrics_sampled,
                'return_diff_pct': return_diff / abs(metrics_full['total_return']) * 100 if metrics_full['total_return'] != 0 else 0,
                'wr_diff': wr_diff,
                'pf_diff_pct': pf_diff / metrics_full['profit_factor'] * 100 if metrics_full['profit_factor'] != 0 else 0,
                'data_reduction': (1 - len(df_sampled) / len(df_full)) * 100
            }
            
            print(f"\n{period_name}:")
            print(f"  Full data: {len(df_full)} candles → {metrics_full['total_return']:.1f}% return, {metrics_full['total_trades']} trades")
            print(f"  Sampled:   {len(df_sampled)} candles → {metrics_sampled['total_return']:.1f}% return, {metrics_sampled['total_trades']} trades")
            print(f"  Data reduction: {validation_results[period_name]['data_reduction']:.1f}%")
            print(f"  Return difference: {validation_results[period_name]['return_diff_pct']:.1f}%")
            print(f"  Win rate difference: {wr_diff:.1f}%")
            print(f"  Profit factor difference: {validation_results[period_name]['pf_diff_pct']:.1f}%")
        
        # Overall assessment
        avg_return_diff = np.mean([v['return_diff_pct'] for v in validation_results.values()])
        avg_data_reduction = np.mean([v['data_reduction'] for v in validation_results.values()])
        
        print("\n" + "="*80)
        print("VALIDATION SUMMARY")
        print("="*80)
        print(f"Average data reduction: {avg_data_reduction:.1f}%")
        print(f"Average return difference: {avg_return_diff:.1f}%")
        
        if avg_return_diff < 10:
            print(f"\n✓ Sampling is VALID - results within 10% margin")
            print(f"  Speedup: ~{1/self.sample_ratio:.1f}x faster")
        else:
            print(f"\n✗ Sampling may not be accurate - consider increasing sample_ratio")
        
        return validation_results
    
    def test_config_sampled(self, config_name, config, timeframe='M5'):
        """Test a configuration using sampled data"""
        results = {}
        
        for period_name in self.test_periods.keys():
            cache_key = self._get_cache_key('XAUUSD', timeframe, self.test_periods[period_name]['days'])
            df = self._load_cached_data(cache_key)
            
            if df is None:
                continue
            
            # Compute indicators on full data (needed for regime identification)
            df = self.compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
            
            # Sample the data
            df_sampled = self._stratified_sample(df, self.sample_ratio)
            
            # Simulate on sampled data
            trades = self.simulate_strategy(df_sampled, config, max_positions=2)
            metrics = self.analyze_results(trades)
            
            if metrics:
                results[period_name] = metrics
        
        return results

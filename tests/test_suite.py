"""
Comprehensive Test Suite for Trading Strategies
- Realistic: Uses real historical data
- Varied: Tests across multiple time periods and market conditions
- Repeatable: Cached data ensures consistent results
- Fast: Parallel execution and data caching
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import pickle
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib

class TestSuite:
    def __init__(self, cache_dir='tests/data_cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Define test periods (varied market conditions)
        self.test_periods = {
            'recent_30d': {'days': 30, 'description': 'Last 30 days'},
            'recent_60d': {'days': 60, 'description': 'Last 60 days'},
            'recent_90d': {'days': 90, 'description': 'Last 90 days'},
            'recent_120d': {'days': 120, 'description': 'Last 120 days'},
            'full_history': {'days': 250, 'description': 'Full available history'}
        }
    
    def _get_cache_key(self, symbol, timeframe, days):
        """Generate cache key for data"""
        # Include current date to invalidate old cache
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
    
    def _save_cached_data(self, cache_key, data):
        """Save data to cache"""
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
    
    def fetch_and_cache_data(self, symbol='XAUUSD', force_refresh=False):
        """Fetch all test data and cache it"""
        print("="*80)
        print("FETCHING AND CACHING TEST DATA")
        print("="*80)
        
        if not mt5.initialize():
            raise Exception(f"MT5 initialization failed: {mt5.last_error()}")
        
        timeframes = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5
        }
        
        cached_data = {}
        
        for tf_name, tf_value in timeframes.items():
            print(f"\nFetching {tf_name} data...")
            
            for period_name, period_info in self.test_periods.items():
                cache_key = self._get_cache_key(symbol, tf_name, period_info['days'])
                
                if not force_refresh:
                    cached = self._load_cached_data(cache_key)
                    if cached is not None:
                        print(f"  {period_name}: Loaded from cache")
                        cached_data[f"{tf_name}_{period_name}"] = cached
                        continue
                
                # Fetch from MT5
                bars_needed = period_info['days'] * 24 * 60 // (5 if tf_name == 'M5' else 1) + 100
                rates = mt5.copy_rates_from_pos(symbol, tf_value, 0, bars_needed)
                
                if rates is None or len(rates) == 0:
                    print(f"  {period_name}: Failed to fetch")
                    continue
                
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                
                # Save to cache
                self._save_cached_data(cache_key, df)
                cached_data[f"{tf_name}_{period_name}"] = df
                
                actual_days = (df['time'].iloc[-1] - df['time'].iloc[0]).days
                print(f"  {period_name}: Fetched {len(df)} bars ({actual_days} days)")
        
        mt5.shutdown()
        
        print(f"\nData cached in: {self.cache_dir}")
        return cached_data

    
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
    
    def test_config(self, config_name, config, timeframe='M5', use_cache=True):
        """Test a configuration across all periods"""
        print(f"\nTesting {config_name} on {timeframe}...")
        
        # Load cached data
        results = {}
        
        for period_name in self.test_periods.keys():
            cache_key = self._get_cache_key('XAUUSD', timeframe, self.test_periods[period_name]['days'])
            df = self._load_cached_data(cache_key)
            
            if df is None:
                print(f"  {period_name}: No cached data (run fetch_and_cache_data first)")
                continue
            
            # Compute indicators
            df = self.compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
            
            # Simulate
            trades = self.simulate_strategy(df, config, max_positions=2)
            metrics = self.analyze_results(trades)
            
            if metrics:
                results[period_name] = metrics
                print(f"  {period_name}: {metrics['total_return']:.1f}% return, {metrics['total_trades']} trades, {metrics['win_rate']:.1f}% WR")
            else:
                print(f"  {period_name}: No trades")
        
        return results
    
    def compare_configs(self, configs_dict, timeframe='M5'):
        """Compare multiple configurations"""
        print("="*80)
        print(f"COMPARING CONFIGURATIONS ON {timeframe}")
        print("="*80)
        
        all_results = {}
        
        for config_name, config in configs_dict.items():
            all_results[config_name] = self.test_config(config_name, config, timeframe)
        
        # Summary comparison
        print("\n" + "="*80)
        print("SUMMARY COMPARISON")
        print("="*80)
        
        for period_name in self.test_periods.keys():
            print(f"\n{period_name.upper()}:")
            print(f"  {'Config':<20} {'Return':<12} {'Trades':<8} {'WR':<8} {'PF':<8} {'Sharpe':<8}")
            print(f"  {'-'*70}")
            
            for config_name in configs_dict.keys():
                if period_name in all_results[config_name]:
                    r = all_results[config_name][period_name]
                    print(f"  {config_name:<20} {r['total_return']:>10.1f}% {r['total_trades']:>7} {r['win_rate']:>6.1f}% {r['profit_factor']:>6.2f} {r['sharpe']:>6.2f}")
                else:
                    print(f"  {config_name:<20} {'N/A'}")
        
        return all_results

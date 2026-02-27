"""
Test Dynamic Position Sizing Strategies
Compares fixed vs dynamic position sizing to optimize risk-adjusted returns
"""
import json
import numpy as np
from test_suite import TestSuite

class DynamicSizingTestSuite(TestSuite):
    """Extended test suite with dynamic position sizing"""
    
    def simulate_strategy_dynamic(self, df, config, max_positions=2, sizing_method='fixed'):
        """
        Simulate strategy with dynamic position sizing
        
        sizing_method options:
        - 'fixed': Current approach (7.5% per position)
        - 'kelly': Kelly Criterion based on recent win rate
        - 'equity_curve': Increase when winning, decrease when losing
        - 'volatility': Adjust based on recent volatility (ATR)
        - 'drawdown': Reduce size during drawdowns
        """
        positions = []
        closed_trades = []
        
        base_position_size = config['position_size_pct'] / max_positions
        leverage = config['leverage']
        
        # Convert to NumPy arrays
        close_prices = df['close'].values
        rsi_values = df['RSI'].values
        atr_values = df['ATR'].values
        uptrend_values = df['uptrend'].values
        downtrend_values = df['downtrend'].values
        
        n_candles = len(close_prices)
        
        # Track equity for dynamic sizing
        equity_curve = [1.0]  # Start at 100%
        recent_trades = []  # Last 20 trades for Kelly calculation
        
        for idx in range(n_candles):
            close = close_prices[idx]
            rsi = rsi_values[idx]
            atr = atr_values[idx]
            uptrend = uptrend_values[idx]
            downtrend = downtrend_values[idx]
            
            # Calculate dynamic position size
            if sizing_method == 'fixed':
                position_size = base_position_size
            
            elif sizing_method == 'kelly':
                # Kelly Criterion: f = (p*b - q) / b
                if len(recent_trades) >= 10:
                    wins = sum(1 for t in recent_trades if t['profit_pct'] > 0)
                    p = wins / len(recent_trades)
                    q = 1 - p
                    
                    # Estimate win/loss ratio
                    winning_trades = [t['profit_pct'] for t in recent_trades if t['profit_pct'] > 0]
                    losing_trades = [abs(t['profit_pct']) for t in recent_trades if t['profit_pct'] <= 0]
                    
                    avg_win = np.mean(winning_trades) if winning_trades else 0.01
                    avg_loss = np.mean(losing_trades) if losing_trades else 0.01
                    b = avg_win / avg_loss if avg_loss > 0 else 1
                    
                    kelly_fraction = (p * b - q) / b if b > 0 else 0
                    kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
                    
                    # Use half-Kelly for safety
                    position_size = (kelly_fraction / 2) / leverage / max_positions
                    position_size = max(position_size, base_position_size * 0.25)  # Min 25% of base
                    position_size = min(position_size, base_position_size * 2.0)   # Max 200% of base
                else:
                    position_size = base_position_size
            
            elif sizing_method == 'equity_curve':
                # Increase size when equity is growing, decrease when falling
                current_equity = equity_curve[-1]
                
                if current_equity > 1.0:
                    # Winning: increase size proportionally (up to 2x)
                    multiplier = min(current_equity, 2.0)
                else:
                    # Losing: decrease size proportionally (down to 0.5x)
                    multiplier = max(current_equity, 0.5)
                
                position_size = base_position_size * multiplier
            
            elif sizing_method == 'volatility':
                # Reduce size when volatility is high
                # Use ATR percentile over last 100 candles
                if idx >= 100:
                    recent_atr = atr_values[max(0, idx-100):idx]
                    atr_percentile = np.percentile(recent_atr, 50)  # Median
                    
                    if atr > atr_percentile * 1.5:
                        # High volatility: reduce size
                        position_size = base_position_size * 0.6
                    elif atr < atr_percentile * 0.7:
                        # Low volatility: increase size
                        position_size = base_position_size * 1.3
                    else:
                        position_size = base_position_size
                else:
                    position_size = base_position_size
            
            elif sizing_method == 'drawdown':
                # Reduce size during drawdowns
                current_equity = equity_curve[-1]
                peak_equity = max(equity_curve)
                drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
                
                if drawdown > 0.10:  # 10% drawdown
                    position_size = base_position_size * 0.5  # Half size
                elif drawdown > 0.05:  # 5% drawdown
                    position_size = base_position_size * 0.75  # 75% size
                else:
                    position_size = base_position_size
            
            # Check exits
            for pos in positions[:]:
                exit_signal = False
                exit_reason = None
                exit_price = None
                
                if pos['type'] == 'LONG':
                    if close >= pos['tp']:
                        exit_signal, exit_reason, exit_price = True, 'TP', pos['tp']
                    elif close <= pos['sl']:
                        exit_signal, exit_reason, exit_price = True, 'SL', pos['sl']
                    elif rsi >= config['rsi_exit_long']:
                        exit_signal, exit_reason, exit_price = True, 'RSI_EXIT', close
                else:  # SHORT
                    if close <= pos['tp']:
                        exit_signal, exit_reason, exit_price = True, 'TP', pos['tp']
                    elif close >= pos['sl']:
                        exit_signal, exit_reason, exit_price = True, 'SL', pos['sl']
                    elif rsi <= config['rsi_exit_short']:
                        exit_signal, exit_reason, exit_price = True, 'RSI_EXIT', close
                
                if exit_signal:
                    if pos['type'] == 'LONG':
                        pnl_pct = (exit_price - pos['entry']) / pos['entry']
                    else:
                        pnl_pct = (pos['entry'] - exit_price) / pos['entry']
                    
                    profit_pct = pnl_pct * leverage * pos['size']
                    
                    trade = {
                        'profit_pct': profit_pct,
                        'exit_reason': exit_reason
                    }
                    closed_trades.append(trade)
                    recent_trades.append(trade)
                    if len(recent_trades) > 20:
                        recent_trades.pop(0)
                    
                    # Update equity curve
                    equity_curve.append(equity_curve[-1] * (1 + profit_pct))
                    
                    positions.remove(pos)
            
            # Check entries
            if len(positions) < max_positions:
                if rsi < config['rsi_buy'] and uptrend:
                    positions.append({
                        'type': 'LONG',
                        'entry': close,
                        'entry_idx': idx,
                        'sl': close - (atr * config['atr_multiplier']),
                        'tp': close * (1 + config['profit_target_pct']),
                        'size': position_size
                    })
                elif config.get('enable_shorts', True) and rsi > config['rsi_sell'] and downtrend:
                    positions.append({
                        'type': 'SHORT',
                        'entry': close,
                        'entry_idx': idx,
                        'sl': close + (atr * config['atr_multiplier']),
                        'tp': close * (1 - config['profit_target_pct']),
                        'size': position_size
                    })
        
        return closed_trades, equity_curve

def test_dynamic_sizing():
    print("="*100)
    print("DYNAMIC POSITION SIZING COMPARISON")
    print("="*100)
    
    suite = DynamicSizingTestSuite()
    
    # Load configs
    with open('config/m5_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_params.json', 'r') as f:
        m1_config = json.load(f)
    
    sizing_methods = {
        'fixed': 'Fixed 7.5% per position (current)',
        'kelly': 'Kelly Criterion (half-Kelly for safety)',
        'equity_curve': 'Equity-based (increase when winning)',
        'volatility': 'Volatility-adjusted (reduce in high vol)',
        'drawdown': 'Drawdown protection (reduce during DD)'
    }
    
    # Test M5
    print("\n" + "="*100)
    print("M5 BOT - DYNAMIC SIZING COMPARISON")
    print("="*100)
    
    m5_results = {}
    
    for method, description in sizing_methods.items():
        print(f"\nTesting: {description}")
        
        # Load data
        cache_key = suite._get_cache_key('XAUUSD', 'M5', 120)
        df = suite._load_cached_data(cache_key)
        df = suite.prepare_indicators(df, m5_config['fast_ema'], m5_config['slow_ema'], m5_config['rsi_period'])
        
        # Simulate with dynamic sizing
        trades, equity_curve = suite.simulate_strategy_dynamic(df, m5_config, max_positions=2, sizing_method=method)
        metrics = suite.analyze_results(trades)
        
        if metrics:
            final_equity = equity_curve[-1]
            max_equity = max(equity_curve)
            max_dd_equity = min((equity_curve[i] - max(equity_curve[:i+1])) / max(equity_curve[:i+1]) 
                               for i in range(1, len(equity_curve)))
            
            m5_results[method] = {
                'metrics': metrics,
                'final_equity': final_equity,
                'max_dd_equity': max_dd_equity * 100
            }
            
            print(f"  Return: {metrics['total_return']:.1f}%")
            print(f"  Final Equity: {final_equity:.3f}x")
            print(f"  Max DD (equity): {max_dd_equity*100:.1f}%")
            print(f"  Sharpe: {metrics['sharpe']:.2f}")
            print(f"  Trades: {metrics['total_trades']}")
    
    # Test M1
    print("\n" + "="*100)
    print("M1 BOT - DYNAMIC SIZING COMPARISON")
    print("="*100)
    
    m1_results = {}
    
    for method, description in sizing_methods.items():
        print(f"\nTesting: {description}")
        
        # Load data
        cache_key = suite._get_cache_key('XAUUSD', 'M1', 60)
        df = suite._load_cached_data(cache_key)
        df = suite.prepare_indicators(df, m1_config['fast_ema'], m1_config['slow_ema'], m1_config['rsi_period'])
        
        # Simulate with dynamic sizing
        trades, equity_curve = suite.simulate_strategy_dynamic(df, m1_config, max_positions=2, sizing_method=method)
        metrics = suite.analyze_results(trades)
        
        if metrics:
            final_equity = equity_curve[-1]
            max_equity = max(equity_curve)
            max_dd_equity = min((equity_curve[i] - max(equity_curve[:i+1])) / max(equity_curve[:i+1]) 
                               for i in range(1, len(equity_curve)))
            
            m1_results[method] = {
                'metrics': metrics,
                'final_equity': final_equity,
                'max_dd_equity': max_dd_equity * 100
            }
            
            print(f"  Return: {metrics['total_return']:.1f}%")
            print(f"  Final Equity: {final_equity:.3f}x")
            print(f"  Max DD (equity): {max_dd_equity*100:.1f}%")
            print(f"  Sharpe: {metrics['sharpe']:.2f}")
            print(f"  Trades: {metrics['total_trades']}")
    
    # Summary comparison
    print("\n" + "="*100)
    print("SUMMARY - BEST METHODS")
    print("="*100)
    
    print("\nM5 Bot:")
    print(f"{'Method':<20} {'Return':<12} {'Equity':<12} {'Max DD':<12} {'Sharpe':<10} {'Trades':<10}")
    print("-"*100)
    
    for method in sizing_methods.keys():
        if method in m5_results:
            r = m5_results[method]
            print(f"{method:<20} {r['metrics']['total_return']:>10.1f}% {r['final_equity']:>10.3f}x "
                  f"{r['max_dd_equity']:>10.1f}% {r['metrics']['sharpe']:>8.2f} {r['metrics']['total_trades']:>9}")
    
    print("\nM1 Bot:")
    print(f"{'Method':<20} {'Return':<12} {'Equity':<12} {'Max DD':<12} {'Sharpe':<10} {'Trades':<10}")
    print("-"*100)
    
    for method in sizing_methods.keys():
        if method in m1_results:
            r = m1_results[method]
            print(f"{method:<20} {r['metrics']['total_return']:>10.1f}% {r['final_equity']:>10.3f}x "
                  f"{r['max_dd_equity']:>10.1f}% {r['metrics']['sharpe']:>8.2f} {r['metrics']['total_trades']:>9}")
    
    # Recommendations
    print("\n" + "="*100)
    print("RECOMMENDATIONS")
    print("="*100)
    
    # Find best by Sharpe ratio (risk-adjusted)
    m5_best = max(m5_results.items(), key=lambda x: x[1]['metrics']['sharpe'])
    m1_best = max(m1_results.items(), key=lambda x: x[1]['metrics']['sharpe'])
    
    print(f"\nBest M5 Method (by Sharpe): {m5_best[0]}")
    print(f"  Return: {m5_best[1]['metrics']['total_return']:.1f}%")
    print(f"  Sharpe: {m5_best[1]['metrics']['sharpe']:.2f}")
    print(f"  Max DD: {m5_best[1]['max_dd_equity']:.1f}%")
    
    print(f"\nBest M1 Method (by Sharpe): {m1_best[0]}")
    print(f"  Return: {m1_best[1]['metrics']['total_return']:.1f}%")
    print(f"  Sharpe: {m1_best[1]['metrics']['sharpe']:.2f}")
    print(f"  Max DD: {m1_best[1]['max_dd_equity']:.1f}%")
    
    # Compare to fixed
    if 'fixed' in m5_results and m5_best[0] != 'fixed':
        improvement = m5_best[1]['metrics']['sharpe'] - m5_results['fixed']['metrics']['sharpe']
        print(f"\nM5 Improvement over fixed: {improvement:+.2f} Sharpe ({improvement/m5_results['fixed']['metrics']['sharpe']*100:+.1f}%)")
    
    if 'fixed' in m1_results and m1_best[0] != 'fixed':
        improvement = m1_best[1]['metrics']['sharpe'] - m1_results['fixed']['metrics']['sharpe']
        print(f"M1 Improvement over fixed: {improvement:+.2f} Sharpe ({improvement/m1_results['fixed']['metrics']['sharpe']*100:+.1f}%)")

if __name__ == '__main__':
    test_dynamic_sizing()

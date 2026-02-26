import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import json

# Import the aggressive backtest function
exec(open('aggressive_strategy.py').read().split('def main()')[0])

def main():
    # Connect and get data
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching maximum available data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data: {len(data)} bars from {data['time'].min()} to {data['time'].max()}")
    days_span = (data['time'].max() - data['time'].min()).days
    print(f"Time span: {days_span} days\n")
    
    # Load the saved aggressive configuration
    with open('config/aggressive_strategy_params.json', 'r') as f:
        config = json.load(f)
    
    print("="*80)
    print("TESTING SAVED AGGRESSIVE STRATEGY")
    print("="*80)
    print(f"Parameters:")
    for key, value in config.items():
        if key != 'strategy':
            print(f"  {key}: {value}")
    
    # Run backtest
    balance, trades, equity = run_aggressive_backtest(
        data, capital=1000,
        fast_ema=config['fast_ema'],
        slow_ema=config['slow_ema'],
        rsi_period=config['rsi_period'],
        rsi_buy=config['rsi_buy'],
        rsi_sell=config['rsi_sell'],
        atr_multiplier=config['atr_multiplier'],
        profit_target_pct=config['profit_target_pct'],
        trailing_stop_pct=config['trailing_stop_pct'],
        enable_shorts=config['enable_shorts'],
        enable_compounding=config['enable_compounding'],
        position_multiplier=config['position_multiplier']
    )
    
    metrics = calculate_metrics(balance, trades, equity, 1000)
    
    if metrics:
        print(f"\nResults:")
        print(f"  Final Balance: ${metrics['balance']:.2f}")
        print(f"  Return: {metrics['return']:.2f}%")
        print(f"  Total Trades: {metrics['trades']}")
        print(f"  Long Trades: {metrics['long_trades']} (Win rate: {metrics['long_win_rate']:.1f}%)")
        print(f"  Short Trades: {metrics['short_trades']} (Win rate: {metrics['short_win_rate']:.1f}%)")
        print(f"  Overall Win Rate: {metrics['win_rate']:.2f}%")
        print(f"  Max Drawdown: {abs(metrics['max_dd']):.2f}%")
        print(f"  Avg Win: ${metrics['avg_win']:.2f}")
        print(f"  Avg Loss: ${metrics['avg_loss']:.2f}")
        print(f"  Risk/Reward Ratio: {metrics['return'] / abs(metrics['max_dd']):.2f}")
        
        # Compare with bidirectional
        print("\n" + "="*80)
        print("COMPARISON WITH BIDIRECTIONAL STRATEGY")
        print("="*80)
        
        with open('config/bidirectional_strategy_params.json', 'r') as f:
            bidir_config = json.load(f)
        
        # Import bidirectional function
        exec(open('bidirectional_strategy.py').read().split('def main()')[0])
        
        bidir_balance, bidir_trades, bidir_equity = run_bidirectional_backtest(
            data, capital=1000,
            fast_ema=bidir_config['fast_ema'],
            slow_ema=bidir_config['slow_ema'],
            rsi_period=bidir_config['rsi_period'],
            rsi_buy=bidir_config['rsi_buy'],
            rsi_sell=bidir_config['rsi_sell'],
            atr_multiplier=bidir_config['atr_multiplier'],
            profit_target_pct=bidir_config['profit_target_pct'],
            enable_shorts=bidir_config['enable_shorts'],
            enable_compounding=bidir_config['enable_compounding']
        )
        
        bidir_metrics = calculate_metrics(bidir_balance, bidir_trades, bidir_equity, 1000)
        
        print(f"\nBidirectional Strategy:")
        print(f"  Return: {bidir_metrics['return']:.2f}%")
        print(f"  Max Drawdown: {abs(bidir_metrics['max_dd']):.2f}%")
        print(f"  Risk/Reward: {bidir_metrics['return'] / abs(bidir_metrics['max_dd']):.2f}")
        
        print(f"\nAggressive Strategy (2x leverage + trailing stops):")
        print(f"  Return: {metrics['return']:.2f}%")
        print(f"  Max Drawdown: {abs(metrics['max_dd']):.2f}%")
        print(f"  Risk/Reward: {metrics['return'] / abs(metrics['max_dd']):.2f}")
        
        print(f"\nDifference:")
        print(f"  Additional Return: {metrics['return'] - bidir_metrics['return']:.2f}%")
        print(f"  Additional Risk: {abs(metrics['max_dd']) - abs(bidir_metrics['max_dd']):.2f}%")
        
        if metrics['return'] > bidir_metrics['return']:
            print(f"\n✓ Aggressive strategy provides {metrics['return'] - bidir_metrics['return']:.2f}% more return")
            print(f"  at the cost of {abs(metrics['max_dd']) - abs(bidir_metrics['max_dd']):.2f}% more drawdown")
        else:
            print(f"\n✗ Bidirectional strategy is better")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()

import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from strategies.scalping import ScalpingStrategy
from backtesting.backtester import Backtester
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import json

def main():
    # Load trading parameters
    with open('config/trading_params.json', 'r') as f:
        config = json.load(f)
    
    # Connect to MT5
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    # Get historical data
    print("Fetching historical data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    data = mt5.get_historical_data(config['symbol'], config['timeframe'], start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data fetched: {len(data)} bars")
    
    # Run backtest
    print("Running backtest...")
    strategy = ScalpingStrategy(config['scalping'])
    backtester = Backtester(strategy, initial_balance=10000)
    results = backtester.run(data, risk_per_trade=config['risk_per_trade'])
    
    # Print results
    print("\n" + "="*50)
    print("BACKTEST RESULTS")
    print("="*50)
    print(f"Total Trades: {results['total_trades']}")
    print(f"Winning Trades: {results['winning_trades']}")
    print(f"Losing Trades: {results['losing_trades']}")
    print(f"Win Rate: {results['win_rate']:.2%}")
    print(f"Total Profit: ${results['total_profit']:.2f}")
    print(f"Gross Profit: ${results['gross_profit']:.2f}")
    print(f"Gross Loss: ${results['gross_loss']:.2f}")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown']:.2%}")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"Final Balance: ${results['final_balance']:.2f}")
    print(f"Return: {results['return_pct']:.2f}%")
    print("="*50)
    
    # Plot equity curve
    plt.figure(figsize=(12, 6))
    plt.plot(results['equity_curve'])
    plt.title('Equity Curve')
    plt.xlabel('Trade Number')
    plt.ylabel('Balance ($)')
    plt.grid(True)
    plt.savefig('results/equity_curve.png')
    print("\nEquity curve saved to results/equity_curve.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()

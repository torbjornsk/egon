import pandas as pd
import numpy as np
import logging
from datetime import datetime

class Backtester:
    def __init__(self, strategy, initial_balance=10000, commission=0.0001):
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.commission = commission
        
    def run(self, data, risk_per_trade=0.02):
        """Run backtest on historical data"""
        df = self.strategy.generate_signals(data)
        
        balance = self.initial_balance
        equity_curve = [balance]
        trades = []
        position = None
        
        for i in range(1, len(df)):
            current_bar = df.iloc[i]
            
            # Close existing position if signal changes
            if position is not None:
                # Check stop loss
                if position['type'] == 'buy':
                    if current_bar['low'] <= position['sl']:
                        pnl = position['sl'] - position['entry_price']
                        balance += pnl * position['size'] - (position['entry_price'] * position['size'] * self.commission * 2)
                        trades.append({**position, 'exit_price': position['sl'], 'exit_time': current_bar['time'], 'pnl': pnl * position['size']})
                        position = None
                    # Check take profit
                    elif current_bar['high'] >= position['tp']:
                        pnl = position['tp'] - position['entry_price']
                        balance += pnl * position['size'] - (position['entry_price'] * position['size'] * self.commission * 2)
                        trades.append({**position, 'exit_price': position['tp'], 'exit_time': current_bar['time'], 'pnl': pnl * position['size']})
                        position = None
                else:  # sell position
                    if current_bar['high'] >= position['sl']:
                        pnl = position['entry_price'] - position['sl']
                        balance += pnl * position['size'] - (position['entry_price'] * position['size'] * self.commission * 2)
                        trades.append({**position, 'exit_price': position['sl'], 'exit_time': current_bar['time'], 'pnl': pnl * position['size']})
                        position = None
                    elif current_bar['low'] <= position['tp']:
                        pnl = position['entry_price'] - position['tp']
                        balance += pnl * position['size'] - (position['entry_price'] * position['size'] * self.commission * 2)
                        trades.append({**position, 'exit_price': position['tp'], 'exit_time': current_bar['time'], 'pnl': pnl * position['size']})
                        position = None
            
            # Open new position on signal
            if position is None and current_bar['signal'] != 0:
                risk_amount = balance * risk_per_trade
                position_size = risk_amount / current_bar['sl_distance']
                
                if current_bar['signal'] == 1:  # Buy
                    position = {
                        'type': 'buy',
                        'entry_price': current_bar['close'],
                        'entry_time': current_bar['time'],
                        'sl': current_bar['close'] - current_bar['sl_distance'],
                        'tp': current_bar['close'] + current_bar['tp_distance'],
                        'size': position_size
                    }
                elif current_bar['signal'] == -1:  # Sell
                    position = {
                        'type': 'sell',
                        'entry_price': current_bar['close'],
                        'entry_time': current_bar['time'],
                        'sl': current_bar['close'] + current_bar['sl_distance'],
                        'tp': current_bar['close'] - current_bar['tp_distance'],
                        'size': position_size
                    }
            
            equity_curve.append(balance)
        
        # Close any remaining position
        if position is not None:
            last_bar = df.iloc[-1]
            if position['type'] == 'buy':
                pnl = last_bar['close'] - position['entry_price']
            else:
                pnl = position['entry_price'] - last_bar['close']
            balance += pnl * position['size']
            trades.append({**position, 'exit_price': last_bar['close'], 'exit_time': last_bar['time'], 'pnl': pnl * position['size']})
        
        return self.calculate_metrics(trades, equity_curve)
    
    def calculate_metrics(self, trades, equity_curve):
        """Calculate performance metrics"""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_profit': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'profit_factor': 0
            }
        
        trades_df = pd.DataFrame(trades)
        
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        total_profit = trades_df['pnl'].sum()
        gross_profit = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
        gross_loss = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
        
        # Calculate max drawdown
        equity_series = pd.Series(equity_curve)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Calculate Sharpe ratio
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        
        return {
            'total_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(trades) if trades else 0,
            'total_profit': total_profit,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'final_balance': equity_curve[-1],
            'return_pct': (equity_curve[-1] - self.initial_balance) / self.initial_balance * 100,
            'equity_curve': equity_curve,
            'trades': trades
        }

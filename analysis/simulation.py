import MetaTrader5 as mt5
import pandas as pd
import datetime

# === CONFIG ===
SYMBOL = "XAUUSD"
CAPITAL = 1000
LEVERAGE = 100
EMA_SPAN = 50
RSI_PERIOD = 10

# Your demo account credentials:
DEMO_LOGIN = 10006621710          # Replace with your demo account number
DEMO_PASSWORD = "W*D1ZnTv"  # Replace with your demo account password
DEMO_SERVER = "MetaQuotes-Demo"  # Replace with your broker's demo server name

def compute_indicators(df):
    df['EMA'] = df['close'].ewm(span=EMA_SPAN).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss = -delta.clip(upper=0).rolling(RSI_PERIOD).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df

def run_backtest(df):
    position = None
    balance = CAPITAL
    trades = []

    for i in range(max(EMA_SPAN, RSI_PERIOD), len(df)):
        row = df.iloc[i]
        price = row['close']
        ema = row['EMA']
        rsi = row['RSI']

        if position is None:
            if rsi < 30:
                position = {'entry': price, 'time': row.name}
                print(f"[{row.name}] BUY at {price:.2f}")
        else:
            entry = position['entry']
            change = (price - entry) / entry
            pnl = change * balance

            # Exit conditions
            if rsi > 70 or change >= 0.03 or (change <= -0.02 and price < ema):
                balance += pnl
                trades.append(pnl)
                print(f"[{row.name}] SELL at {price:.2f} | PnL: {pnl:.2f} | New balance: {balance:.2f}")
                position = None

            if balance <= 0:
                print("Account blown!")
                break

    # Final result
    print("\n--- BACKTEST SUMMARY ---")
    print(f"Initial capital: ${CAPITAL:.2f}")
    print(f"Final balance:   ${balance:.2f}")
    print(f"Total trades:    {len(trades)}")
    print(f"Net PnL:         ${sum(trades):.2f}")
    if trades:
        print(f"Average PnL:     ${sum(trades)/len(trades):.2f}")
        print(f"Win rate:        {100 * sum(1 for x in trades if x > 0) / len(trades):.2f}%")

def main():
    # Initialize and login to MT5
    if not mt5.initialize():
        print("MT5 initialize() failed. Trying login...")
        if not mt5.login(DEMO_LOGIN, password=DEMO_PASSWORD, server=DEMO_SERVER):
            print("Login failed:", mt5.last_error())
            return

    # Fetch data
    print("Fetching 1-minute bars for the past month...")
    from_date = datetime.datetime.now() - datetime.timedelta(days=30)
    to_date = datetime.datetime.now()
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, from_date, to_date)

    if rates is None or len(rates) == 0:
        print("Failed to retrieve historical data")
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)

    df = compute_indicators(df)
    run_backtest(df)

    mt5.shutdown()

if __name__ == "__main__":
    main()

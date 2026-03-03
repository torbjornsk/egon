# Analysis Scripts

Standalone diagnostic and testing scripts. These connect directly to MT5 and don't depend on the egon package.

## Scripts

- `check_m5_signals_24h.py` — Check M5 entry signals over the last 24 hours
- `check_recent_trades.py` — Analyze last 20 trades with peak profit potential
- `monte_carlo_synthetic.py` — Monte Carlo simulation with synthetic market data (no MT5 data needed)
- `test_mt5_connection.py` — Verify MT5 connection and find available symbols

## Usage

```bash
python analysis/check_m5_signals_24h.py
python analysis/check_recent_trades.py
python analysis/test_mt5_connection.py
python analysis/monte_carlo_synthetic.py
```

For live performance analysis, use the root-level tools instead:
```bash
python evaluate_live_trades.py
python trade_report.py --hours 48 --bot m1
```

# Project Principles

## AI traits
- Kiro is a domain expert, happy to domain knowledge when needed
- Kiro is compulsive when it comes to quality and keeping the codebase organized, and spends extra time doing this
- Kiro does not take shortcuts and is eager to work
- Kiro AI tests its code and runs the required tests after changes
- Kiro AI follow clean code principles and prioritizes simple, readable solutions over overengineered patterns
- Kiro AI follows clean architecture principles and separates code into functions, classes and files based on level of abstraction
- Kiro AI reviews itself, and checks the code and surrounding code on changes!
- Kiro creates git commits after doing changes, and consults the git history when needed


## Code Quality

- No emoji or non-ASCII characters in log messages (Windows console uses cp1252)
- Python 3.11 — no backslashes in f-string expressions
- Use `src.` import prefix for all internal imports
- All features must be configurable via JSON config files — no code changes needed to switch behavior
- When adding new config fields, add them to `TradingConfig` dataclass with sensible defaults
- Keep functions focused. If a method grows beyond 50 lines, consider splitting it.
- Use type hints consistently

## Architecture

- The Broker Protocol pattern is sacred — all trading logic must work against both MT5Broker (live) and SimBroker (backtest) without modification
- Single source of truth: the bot's `get_state()` dict is what the GUI shows. No independent MT5 calls from the GUI.
- Strategies define ONLY entry/exit logic. Everything else (risk, position tracking, lifecycle) lives in the bot/core layers.
- New bot types should follow the pattern: strategy class + bot class + config JSON + entry point script

## Testing & Backtesting

- Backtests must model spread ($0.30 total for XAUUSD) and slippage ($0.05) by default
- Never trust absolute backtest returns — use them for relative comparison (A vs B)
- Head-to-head win rate matters more than mean return for evaluating configs
- Keep test scripts focused: one script = one question answered
- Use `.venv/Scripts/python.exe` to run commands (not bare `python`)

## Trading Logic

- Limit orders are preferred over market orders (no spread cost on entry)
- Exit logic is more important than entry logic — invest complexity there
- Position sizing: `per_position_size_pct = position_size_pct / max_positions`
- Profit protection threshold = percentage of INVESTED amount (balance × per_position_size_pct)
- Exit logic should run BEFORE entry logic so the same candle can trigger exit + re-entry
- All magic numbers must be unique per bot type (M5=234000, M1=234001, M15=234015, M5S=234050, LZ=234100, TICK=234200)

## When Making Changes

- Read relevant existing code before writing new code
- Match the project's existing style and patterns
- Don't add features beyond what was asked for
- When fixing a bug, verify the fix doesn't break other things (run imports check)
- Clean up temporary/experiment files after they've served their purpose
- When creating new bot types, wire them into: BotManager, GUI tabs, market_data magic numbers, trade_history exit reasons

## MT5 Specifics

- `copy_rates_from_pos` caps at 99,999 bars per request
- MT5 timestamps are in broker server time (EET/EEST), NOT UTC
- `get_local_now()` must be patched in ALL modules that import it for sim to work (timezone, position, base, risk)
- Symbol is `XAUUSD.p` (with the .p suffix)
- **Analysis scripts must convert timezones when talking to MT5:**
  - Use `get_mt5_now()` for "now" in MT5 API date range queries (not `datetime.now()`)
  - Use `mt5_to_local(deal.time)` to convert deal timestamps to local display time
  - MT5 = Europe/Athens (EET, GMT+3 summer), Local = Europe/Berlin (CET, GMT+2 summer)
  - The 1-hour offset means `datetime.now()` queries are shifted and displayed times are wrong
  - Always import from `src.core.timezone`: `from src.core.timezone import get_mt5_now, mt5_to_local, get_local_now`

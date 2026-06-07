.PHONY: install dev lint format clean m1 m5 gui backtest monte-carlo compare replay

install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

lint:
	ruff check src/
	mypy src/

format:
	black src/ run_m1.py run_m5.py run_gui.py
	ruff check --fix src/

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

m1:
	python run_m1.py

m5:
	python run_m5.py

gui:
	python run_gui.py

# Testing
backtest:
	python -m tests.run_backtest --bot m5 --days 90

monte-carlo:
	python -m tests.run_monte_carlo --bot m5 --runs 200 --days 365

compare:
	python -m tests.run_comparison --bot m5 --config-a config/m5_params.json --config-b config/m5_params.json --runs 100

replay:
	python -m tests.run_replay --bot m5 --hours 24

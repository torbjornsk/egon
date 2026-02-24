.PHONY: install dev test lint format clean run backtest optimize

install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

notebook:
	uv pip install -e ".[notebook]"

test:
	pytest

lint:
	ruff check src/ examples/
	mypy src/

format:
	black src/ examples/
	ruff check --fix src/ examples/

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run:
	python src/bot.py

backtest:
	python examples/run_backtest.py

optimize:
	python examples/optimize_parameters.py

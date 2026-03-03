.PHONY: install dev lint format clean m1 m5 gui

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

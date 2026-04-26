.PHONY: help install lint format test check bootstrap clean

help:
	@echo "ZeroBot — common targets"
	@echo "  make install     install runtime + dev dependencies (editable)"
	@echo "  make lint        run ruff in check mode"
	@echo "  make format      auto-format with ruff"
	@echo "  make test        run the pytest suite"
	@echo "  make check       lint + format-check + tests (pre-commit gate)"
	@echo "  make bootstrap   run the database bootstrap script (init + migrate + seed)"
	@echo "  make clean       remove caches and build artifacts"

install:
	pip install -e ".[dev]"

lint:
	ruff check zerobot tests

format:
	ruff format zerobot tests

test:
	pytest

check: lint
	ruff format --check zerobot tests
	pytest

bootstrap:
	python -m zerobot.main

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

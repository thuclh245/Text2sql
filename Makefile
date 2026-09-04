PYTHON ?= .venv/bin/python
UV ?= .venv/bin/uv

.PHONY: install test lint format-check typecheck check

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev]' uv
	UV_CACHE_DIR=.uv-cache $(UV) sync --dev

test:
	$(PYTHON) -m pytest

lint:
	.venv/bin/ruff check .

format-check:
	.venv/bin/ruff format --check .

typecheck:
	.venv/bin/mypy src/chatsql

check: lint format-check typecheck test

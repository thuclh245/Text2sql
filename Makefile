PYTHON ?= .venv/bin/python
UV ?= .venv/bin/uv

.PHONY: install test lint typecheck check

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev]' uv
	UV_CACHE_DIR=.uv-cache $(UV) sync --dev

test:
	$(PYTHON) -m pytest

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy src/chatsql

check: lint typecheck test

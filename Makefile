.PHONY: setup dev test lint format typecheck build check

UV := $(if $(wildcard .tools/bin/uv),.tools/bin/uv,uv)
UV_CACHE_DIR ?= /tmp/solora-uv-cache
export UV_CACHE_DIR

setup:
	$(UV) sync --extra dev

dev:
	$(UV) run uvicorn solora.app:app --app-dir backend/src --reload

test:
	$(UV) run pytest

lint:
	$(UV) run ruff format --check .
	$(UV) run ruff check .

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:
	$(UV) run mypy

build:
	$(UV) build

check: lint typecheck test build

.PHONY: setup dev-backend dev-frontend test lint format typecheck build check

UV := $(if $(wildcard .tools/bin/uv),.tools/bin/uv,uv)
UV_CACHE_DIR ?= /tmp/solora-uv-cache
export UV_CACHE_DIR
PNPM ?= pnpm

setup:
	$(UV) sync --extra dev --locked
	$(PNPM) --dir frontend install --frozen-lockfile

dev-backend:
	$(UV) run uvicorn solora.app:app --app-dir backend/src --reload

dev-frontend:
	$(PNPM) --dir frontend dev

test:
	$(UV) run pytest
	$(PNPM) --dir frontend test

lint:
	$(UV) run ruff format --check .
	$(UV) run ruff check .
	$(PNPM) --dir frontend lint

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:
	$(UV) run mypy
	$(PNPM) --dir frontend typecheck

build:
	$(UV) build
	$(PNPM) --dir frontend build

check: lint typecheck test build

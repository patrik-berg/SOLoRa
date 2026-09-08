.PHONY: setup setup-radio migrate run demo-two-nodes transport-info transport-radio dev-backend dev-frontend test lint format typecheck build check

UV := $(if $(wildcard .tools/bin/uv),.tools/bin/uv,uv)
UV_CACHE_DIR ?= /tmp/solora-uv-cache
export UV_CACHE_DIR
PNPM := $(if $(wildcard .tools/bin/pnpm),PATH="$(CURDIR)/.tools/bin:$$PATH" .tools/bin/pnpm,pnpm)

setup:
	$(UV) sync --extra dev --locked
	$(PNPM) --dir frontend install --frozen-lockfile

setup-radio:
	$(UV) sync --extra dev --extra radio --locked

migrate:
	mkdir -p data
	$(UV) run alembic -c backend/alembic.ini upgrade head

run: build migrate
	$(UV) run uvicorn solora.app:app --app-dir backend/src --host 127.0.0.1 --port 8000

.PHONY: desktop runtime-server
desktop:
	$(PNPM) --dir frontend build
	$(UV) run solora desktop

runtime-server:
	$(PNPM) --dir frontend build
	$(UV) run solora server

demo-two-nodes:
	$(UV) run python -m solora.demo_two_nodes

transport-info:
	$(UV) run python -m solora.transport_cli

transport-radio:
	$(UV) run --extra radio python -m solora.transport_cli --transport meshtastic-serial

dev-backend: migrate
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

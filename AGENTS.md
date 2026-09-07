# Repository Guidelines

## Project Structure & Module Organization

Keep the root limited to project-wide configuration and documentation. The repository is organized as follows:

- `backend/src/solora/` contains the FastAPI API, domain code, and adapters.
- `frontend/src/` contains the React/TypeScript client; keep UI tests beside components.
- `protocol/` contains protocol design notes, schemas, and byte-level fixtures.
- `tests/` contains cross-component and integration tests; component-local unit tests may live beside their source.
- `.github/workflows/` contains CI and automation definitions.
- `ARCHITECTURE.md`, `PROTOCOL.md`, and `ROADMAP.md` document system design, wire behavior, and planned work.

Prefer small, focused modules. Avoid placing generated output, dependency caches, credentials, or editor-specific files under version control.

## Build, Test, and Development Commands

Use `make setup` to install Python and frontend dependencies. Run `make dev-backend` and `make dev-frontend` for local development. `make test`, `make lint`, `make typecheck`, and `make build` cover both applications. `make check` runs the complete pre-push suite.

Before submitting work, run every configured formatter, linter, test suite, and build command locally. Commands should be reproducible from the repository root.

Before declaring a feature, bug fix, or substantial change complete, review every applicable item in `CHECKLIST.md` and resolve any unmet item.

## Coding Style & Naming Conventions

Target Python 3.12 and Node.js 24. Ruff controls Python formatting with 4-space indentation and a 100-character line limit; Oxlint and TypeScript check the frontend. Use `snake_case` for Python, `PascalCase` for React components and classes, and `camelCase` for TypeScript functions. Keep domain code independent of frameworks and adapters.

## Testing Guidelines

Add pytest tests with every behavior change or bug fix. Name tests after observable behavior, such as `test_rejects_expired_token`. CI enforces at least 90% coverage. Tests must be deterministic; replace network, clock, filesystem, and radio hardware dependencies with fixtures or fakes.

## Commit & Pull Request Guidelines

Use concise Conventional Commit subjects, for example `feat: add radio discovery` or `fix: validate empty device ID`.

Pull requests should explain the problem and solution, list verification performed, and link relevant issues. Include screenshots or logs for visible behavior changes. Keep changes narrowly scoped, call out configuration or compatibility impacts, and never commit secrets; provide sanitized examples such as `.env.example` instead.

## Product and Release Rules

Communicate product-facing summaries in concise Swedish. Keep protocol changes synchronized with `PROTOCOL.md` and milestones with `ROADMAP.md`. Beta versions use `v0.x.x-beta.N`. Never publish or promote a stable release without explicit manual approval from the product owner.

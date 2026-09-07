# Repository Guidelines

## Project Structure & Module Organization

Keep the root limited to project-wide configuration and documentation. The repository is organized as follows:

- `backend/` contains server-side services and protocol integrations.
- `frontend/` contains the user-facing application.
- `tests/` contains cross-component and integration tests; component-local unit tests may live beside their source.
- `.github/workflows/` contains CI and automation definitions.
- `ARCHITECTURE.md`, `PROTOCOL.md`, and `ROADMAP.md` document system design, wire behavior, and planned work.

Prefer small, focused modules. Avoid placing generated output, dependency caches, credentials, or editor-specific files under version control.

## Build, Test, and Development Commands

No build system or package manager has been configured yet. When introducing one, expose the common workflow through a small, documented command set—for example `make setup`, `make test`, `make lint`, and `make build`, or equivalent package scripts. Update this section and `README.md` in the same change.

Before submitting work, run every configured formatter, linter, test suite, and build command locally. Commands should be reproducible from the repository root.

## Coding Style & Naming Conventions

Follow the standard formatter and linter for the chosen language; commit their configuration when source code is first added. Use spaces rather than tabs unless the formatter requires otherwise. Choose descriptive names: `snake_case` for files where language conventions permit, `PascalCase` for types, and `camelCase` for functions and variables. Keep public APIs documented and avoid unrelated formatting changes.

## Testing Guidelines

Add tests with each behavior change or bug fix. Mirror production paths and use names that describe observable behavior, such as `test_rejects_expired_token`. Keep tests deterministic and isolate network or external-service dependencies with fixtures or fakes. Any future coverage threshold must be enforced in CI and documented here.

## Commit & Pull Request Guidelines

No Git history is available to establish an existing convention. Use concise, imperative commit subjects, optionally following Conventional Commits (for example, `feat: add radio discovery` or `fix: validate empty device ID`).

Pull requests should explain the problem and solution, list verification performed, and link relevant issues. Include screenshots or logs for visible behavior changes. Keep changes narrowly scoped, call out configuration or compatibility impacts, and never commit secrets; provide sanitized examples such as `.env.example` instead.

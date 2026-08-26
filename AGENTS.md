# Repository Guidelines

## Project Structure & Module Organization

This is an async Python package targeting Python 3.11+. The public FastAPI
adapter is in `govbr_auth/fastapi.py`; shared composition and protocol logic
are under `govbr_auth/core/`, and the local FakeGov provider is under
`govbr_auth/fake/`. Keep runnable examples in `examples/` and Sphinx sources
in `docs/`. Tests are organized by purpose: `tests/unit/`,
`tests/integration/`, `tests/contract/`, and `tests/test_django_auth/`.

## Build, Test, and Development Commands

Create and activate a virtual environment, then install development
dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the complete test suite:

```bash
python -m pytest --tb=short --disable-warnings -q
```

Format Python files with Black and run the CI-blocking lint checks:

```bash
black govbr_auth tests examples
flake8 govbr_auth tests examples --count --select=E9,F63,F7,F82 --show-source --statistics
```

Build distribution artifacts with `python -m build`. To exercise the local
FakeGov flow, set `GOVBR_FAKE_END_TO_END=true` and run
`python -m govbr_auth.fake`.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, async APIs where appropriate, and
Black formatting. Use `snake_case` for modules, functions, and variables;
`PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Preserve the
framework-neutral boundary in `core/`: core modules must not import FastAPI.

## Testing Guidelines

Use pytest with `pytest-asyncio`, and name files and tests `test_*.py` and
`test_*`. Add or update tests for every behavior change, especially changes
to authentication, JWT validation, redirects, cookies, state, or PKCE.

## Commit & Pull Request Guidelines

Use short Conventional Commit subjects such as `fix(runtime): validate prefix`
or `docs(fake): clarify setup`. Keep branches focused, describe the problem
and solution, link the relevant issue, list validation commands, and disclose
security or compatibility impact. Update documentation and `CHANGELOG.md`
when user-visible behavior changes. Never include real credentials, tokens,
keys, or user data.

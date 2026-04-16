# Contributing to Aether Forge

Thanks for your interest in contributing to Aether Forge!

## Getting Started

```bash
git clone https://github.com/HeyElsa/aether-forge.git
cd aether-forge
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[all,dev]'
```

## Running Tests

```bash
pytest tests/ -x --tb=short
```

## Linting

```bash
ruff check src/ tests/
```

## Validating

```bash
forge validate examples/delta-neutral-btc/
forge doctor
```

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Run `pytest` and `ruff check` — both must pass
5. Open a PR against `main`

## Code Style

- Python 3.12+
- Type hints on public functions
- No unnecessary dependencies — the core has only `jsonschema`
- Security-sensitive code gets file permission enforcement (0600/0700)
- All SQL uses parameterized queries (`?` placeholders)

## Reporting Security Issues

Do **not** open a public issue for security vulnerabilities. Email ask@heyelsa.ai with details and we'll respond within 48 hours.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

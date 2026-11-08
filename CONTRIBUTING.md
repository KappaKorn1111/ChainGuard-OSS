# Contributing to ChainGuard OSS

## Development setup

Install Docker with Compose v2, copy `.env.example` to `.env`, and replace the example
passwords. Start the complete stack with `./scripts/bootstrap.sh`.

For host-side checks:

```bash
cd backend
uv sync --dev
uv run ruff check .
uv run pytest ../tests

cd ../frontend
npm ci
npm run lint
npm run build
```

## Change expectations

- Add reversible Alembic migrations for every schema change.
- Preserve raw scanner evidence and provenance; never fabricate findings.
- Keep secrets out of source control and logs.
- Invoke external tools without a shell and retain explicit time/resource bounds.
- Add or update contract tests when an API response changes.
- Update `docs/architecture.md` when a component or trust boundary changes.

Use focused commits and include verification commands and any unverified integration in
the pull request description.

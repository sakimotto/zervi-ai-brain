# AGENTS.md — Zervi AI Brain

## Project overview

This is the **Saki AI Brain**: a FastAPI service that powers the embedded AI assistant in Zervi's Odoo ERP.

- **Runtime:** Python 3.12 + FastAPI + Uvicorn
- **Database:** PostgreSQL with the `pgvector` extension
- **LLM:** DeepSeek (`deepseek-v4-pro` by default)
- **Embeddings:** OpenAI-compatible API (`text-embedding-3-small` by default)
- **Migrations:** Alembic (async, `asyncpg`)
- **Deployment:** Docker Compose on Elestio / CloudPepper

The repo is included as a Git submodule inside `sakimotto/odoo-local` at `odoo-local/ai_brain/`.

## Repository layout

```
app/
  main.py          # FastAPI endpoints, LLM calls, tool validation, SSE streaming
  config.py        # Environment configuration and secrets
  models.py        # SQLAlchemy / pgvector models
  crud.py          # Database operations and default agent/skill seeding
  seed_data.py     # Department prompts and sample RAG documents/facts
  db.py            # Async engine and session factory
  rate_limit.py    # In-memory sliding-window rate limiter
migrations/        # Alembic migrations
tests/             # pytest suite
```

## Required environment variables

The following secrets must be set at runtime. **Never commit them to Git.**

| Variable | Purpose |
|---|---|
| `DATABASE_URL` / `POSTGRES_URI` | PostgreSQL + asyncpg connection string |
| `PGVECTOR_URI` | Usually the same as `DATABASE_URL` |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | Default: `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | Default: `deepseek-v4-pro` |
| `OPENAI_API_KEY` | OpenAI/OpenRouter key for embeddings |
| `OPENAI_BASE_URL` | Default: `https://api.openai.com/v1` |
| `AI_ASSISTANT_SECRET` | Shared secret used by the Odoo frontend |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (prod should be explicit) |

See `.env.example` for the template.

## Local development

### Run tests

```bash
cd odoo-local/ai_brain
.venv/Scripts/python -m pytest -q
```

Expected: `15 passed`.

### Build the Docker image (smoke test)

```bash
cd odoo-local/ai_brain
docker compose -f docker-compose.prod.yml build
```

This only verifies the image builds. Running the container locally requires a PostgreSQL/pgvector database and all secrets.

## Branch and release workflow

This repo follows the same flow as `odoo-local`:

1. Branch from `develop` for features/fixes.
2. Open a PR to `develop`.
3. PR checks run `py_compile` and `pytest`.
4. Merge to `develop` for integration.
5. Merge to `main` for production.
6. Production deploy is **manual** via `.github/workflows/deploy-prod.yml` (`workflow_dispatch`).
7. After release, update the `ai_brain` submodule pointer in `odoo-local` so Odoo modules are pinned to a known brain commit.

## Safety rules

- Do **not** commit secrets, `.env` files, or SSH keys.
- Do **not** deploy to production without running tests first.
- Do **not** change model defaults without checking `config.py`, `docker-compose.prod.yml`, `elestio.yml`, and `.env.example` for consistency.
- Production deploys require explicit approval and a health check after deploy.
- If a change affects the database schema, add an Alembic migration and test it against a backup first.

## Common failure modes and rollback

| Issue | Likely cause | Rollback |
|---|---|---|
| App fails to start | Missing `AI_ASSISTANT_SECRET` or `DATABASE_URL` | Set env vars and restart |
| Alembic fails | DB unreachable or migration conflict | Revert code, restore DB from backup if migration ran |
| DeepSeek errors | API key / model / rate limit | Override `DEEPSEEK_MODEL` env var or revert commit |
| CORS errors | `ALLOWED_ORIGINS` missing or wrong | Update env and redeploy |

For simple doc/config changes, revert the commit and redeploy:

```bash
git revert <commit-hash>
```

No database rollback is needed for documentation or default-value changes.

## Related repos

- `sakimotto/odoo-local` — CloudPepper workflows and Odoo module `ai_assistant_ui`
- `sakimotto/odoo-migration-v17-to-v19` — Custom Odoo modules
- `sakimotto/zervi-ai-toolkit` — Agent skills

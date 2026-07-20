# Agent Collaboration Rules — Zervi AI Brain

This file governs every AI agent working in this repository. User instructions given directly in conversation always take precedence, but these rules are defaults.

## Before You Do Anything Else

1. Read this file.
2. Read `docs/tasks.md` for current focus and blockers.
3. Read `docs/inventory.md` for the environment map.
4. Read `source/skills/zak-vervi/SKILL.md` in the AI Toolkit for Zervi constitution.
5. Read the latest handover in `docs/onboarding/` if one exists.
6. Run the session-start protocol from the AI Toolkit.

## What Is This Repo

**Zervi AI Brain** — the FastAPI backend that powers Saki, the AI assistant embedded in Zervi's Odoo ERP. It handles chat, streaming, tool execution, RAG memory, agent management, and LLM communication with DeepSeek.

## Key Rules

- **Never commit secrets.** API keys live in Infisical, not in code or `.env`.
- **`.env.example` documents placeholders only.** Never put real values there.
- **Brain is stateless except for the database.** Migrations run on startup.
- **All endpoints except `/health` require `X-AI-Assistant-Secret` header.**
- **Production deployments go through PR → merge to main → GitHub Actions deploy.**
- **Do not push directly to main.** Use feature branches and PRs.
- **Before deploying, test locally with `docker-compose.prod.yml`.**

## Architecture

```
Odoo UI (ai_assistant_ui module)
    │
    ▼
Brain (FastAPI, this repo) ─── DeepSeek LLM
    │                           │
    ├── /chat (streaming)       ├── Embeddings (OpenAI)
    ├── /suggest                ├── pgvector (RAG)
    ├── /agents                 │
    ├── /documents              └── Retry/backoff
    └── /facts
         │
         ▼
    PostgreSQL + pgvector
```

## Coding Standards

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy async
- All endpoints validate `X-AI-Assistant-Secret` (except `/health`)
- Tool requests validated against agent skill schemas
- Retry/backoff on transient DeepSeek errors
- Alembic for migrations — run on startup via lifespan

## When to Escalate

Stop and involve Zak if the task touches:
- Elestio hosting, DNS, or deployment config
- DeepSeek API key or Infisical secrets
- New LLM vendor or model provider
- Database schema changes that need migration
- Production deployment

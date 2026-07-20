# AI Brain — Environment Inventory

**Updated:** 2026-07-20

## Deployment

| Property | Value |
|----------|-------|
| Service | FastAPI on Elestio |
| Production URL | `https://zervi-ai-brain-u34072.vm.elestio.app` |
| Health check | `/health` → `{"status": "ok", "database": "connected"}` |
| Auth | `X-AI-Assistant-Secret` header on all endpoints except `/health` |
| CI/CD | GitHub Actions — merge to main → auto-deploy |

## Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12+ | Runtime |
| FastAPI | latest | Web framework |
| Pydantic | v2 | Validation |
| SQLAlchemy | async | ORM |
| pgvector | latest | Vector embeddings |
| Alembic | latest | Migrations |
| httpx | latest | HTTP client for DeepSeek |
| OpenAI SDK | latest | Embeddings API |

## LLM Configuration

| Setting | Value |
|---------|-------|
| Provider | DeepSeek |
| Model | `deepseek-chat` (v4-pro) |
| Base URL | `https://api.deepseek.com` |
| Max tokens (chat) | 4096 |
| Max tokens (suggest) | 512 |
| Retry attempts | 3 |
| Retry backoff | 1.0s exponential |

## Embedding Configuration

| Setting | Value |
|---------|-------|
| Provider | OpenAI |
| Model | text-embedding-3-small |
| Dimension | 1536 |
| Similarity threshold | 0.75 |

## Database

| Property | Value |
|----------|-------|
| Engine | PostgreSQL + pgvector |
| Tables | chat_sessions, chat_messages, message_embeddings, ai_agents, ai_skills, agent_skill_link, documents, facts |

## Agents (8)

| ID | Name | Skills | Active |
|----|------|--------|--------|
| 1 | Zervi AI (Default) | All | ✅ |
| 2 | Sales Agent | Sales + Low Risk + Search + Invoicing | ✅ |
| 3 | Purchasing Agent | Purchasing + Low Risk + Search | ✅ |
| 4 | Accounting Agent | Accounting + Low Risk + Search + Invoicing | ✅ |
| 5 | Warehouse Agent | Warehouse + Low Risk + Search + Inventory | ✅ |
| 6 | Manufacturing Agent | Manufacturing + Low Risk + Search | ✅ |
| 7 | Engineering Agent | Engineering + Low Risk + Search | ✅ |
| 8 | HR Agent | HR + Low Risk + Search | ✅ |

## Tools (18)

search_records, count_records, create_activity, post_chatter_message, confirm_sales_order, validate_picking, done_manufacturing_order, confirm_purchase_order, create_invoice, get_coa_summary, get_inventory_valuation_setup, search_engineering_documents, list_open_engineering_tasks, create_engineering_project, add_engineering_task, link_bom_to_project, create_engineering_document, create_engineering_document_revision

## RAG Knowledge

| Type | Count | Source |
|------|-------|--------|
| Documents | 8 | Playbooks, SOPs, policies (seeded) |
| Facts | 15 | Business rules, thresholds (seeded) |

## Environment Variables

See `.env.example` for full list. Key variables:

- `DEEPSEEK_API_KEY` — LLM API key (from Infisical)
- `OPENAI_API_KEY` — Embeddings API key
- `AI_ASSISTANT_SECRET` — Shared secret with Odoo
- `DATABASE_URL` — PostgreSQL connection string
- `ALLOWED_ORIGINS` — CORS origins (Odoo frontend URLs)

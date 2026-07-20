# Zervi AI Brain — Saki's Backend

FastAPI backend for Saki, the context-aware AI assistant embedded in Zervi's Odoo ERP. Handles chat, streaming, tool execution, RAG memory, and agent management.

## Quick Start

```bash
# Clone
git clone https://github.com/sakimotto/zervi-ai-brain.git
cd zervi-ai-brain

# Set up environment
cp .env.example .env
# Edit .env with your DeepSeek API key and OpenAI key (for embeddings)

# Install
pip install -r requirements.txt

# Run migrations + start
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Architecture

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI (Python 3.12+) |
| LLM | DeepSeek v4-pro (via OpenAI-compatible API) |
| Embeddings | OpenAI text-embedding-3-small |
| Vector DB | PostgreSQL + pgvector |
| Migrations | Alembic |
| Deployment | Docker on Elestio |

## Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | None | Health check + DB status |
| `/chat` | POST | Secret | Non-streaming chat |
| `/chat/stream` | POST | Secret | SSE streaming chat |
| `/chat/analyze` | POST | Secret | One-shot analysis, no persistence |
| `/suggest` | POST | Secret | Proactive context-aware suggestions |
| `/agents` | GET/POST | Secret | List/create AI agents |
| `/agents/{id}` | GET | Secret | Agent detail with skills |
| `/sessions` | GET | Secret | List chat sessions |
| `/documents` | GET/POST | Secret | RAG document management |
| `/facts` | GET/POST | Secret | RAG fact management |

## Agents

7 departmental agents + 1 default:

| Agent | Domain | Skills |
|-------|--------|--------|
| Default (Saki) | All domains, all tools | All |
| Sales Agent | Quotations, orders, customers, invoices | Sales + Low Risk + Search + Invoicing |
| Purchasing Agent | RFQs, POs, vendors, receipts | Purchasing + Low Risk + Search |
| Accounting Agent | Invoices, payments, reconciliation | Accounting + Low Risk + Search + Invoicing |
| Warehouse Agent | Pickings, stock, transfers | Warehouse + Low Risk + Search + Inventory |
| Manufacturing Agent | MOs, BOMs, work orders | Manufacturing + Low Risk + Search |
| Engineering Agent | Patterns, CAD, drawings, revisions | Engineering + Low Risk + Search |
| HR Agent | Employees, contracts, leave | HR + Low Risk + Search |

## RAG Memory

- Messages: embedded per user session, semantic search
- Documents: 8 seeded (playbooks, SOPs, policies)
- Facts: 15 seeded (business rules, thresholds, deadlines)
- All embeddings via pgvector, scoped per user

## Deployment

Production URL: `https://zervi-ai-brain-u34072.vm.elestio.app`

Deploy via GitHub Actions: merge to main → auto-deploy to Elestio.

## License

Proprietary — Zervi Group. All rights reserved.

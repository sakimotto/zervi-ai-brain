# Saki — Zervi's AI Assistant Brain

The backend service that powers **Saki**, the AI assistant embedded in Zervi's Odoo ERP. Saki helps Zervi's team — warehouse staff, sales, purchasing, manufacturing, accounting, engineering, and HR — get their work done faster by understanding what's on their screen and taking action.

## What Saki Can Do

- **Answer questions** about any Odoo record — "What's the status of this sales order?"
- **Search and look up** data — "Show me all open purchase orders"
- **Execute actions** — confirm orders, validate pickings, mark manufacturing done, post notes
- **Suggest next steps** — Saki sees what screen you're on and suggests what to do next
- **Remember context** — Saki recalls past conversations and company policies
- **Switch personas** — 7 specialist agents: Sales, Purchasing, Accounting, Warehouse, Manufacturing, Engineering, HR

## Architecture

```
Odoo Chat Panel  →  Brain (this service)  →  DeepSeek AI
                        │
                   PostgreSQL + pgvector (memory)
```

- **Framework:** FastAPI (Python)
- **AI Model:** DeepSeek v4-pro
- **Memory:** Vector search across past conversations, company documents, and business rules
- **Deployment:** Docker on Elestio, auto-deployed when code is merged

## Setup (Developers)

```bash
git clone https://github.com/sakimotto/zervi-ai-brain.git
cd zervi-ai-brain
cp .env.example .env    # add your API keys
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Related Projects

- **Odoo Module** — `ai_assistant_ui` in [odoo-migration-v17-to-v19](https://github.com/sakimotto/odoo-migration-v17-to-v19) — the chat panel users see
- **AI Toolkit** — [zervi-ai-toolkit](https://github.com/sakimotto/zervi-ai-toolkit) — rules, skills, and agent governance

## Team

Built and maintained by **Zak** (Lead Software & Technology) for **Zervi Group** — custom car seat cover manufacturing, Thailand.

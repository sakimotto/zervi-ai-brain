# Saki Brain — Project Specification

**Date:** 2026-07-20
**Version:** 0.3.1
**Owner:** Zak
**Status:** Active development

## Purpose

Saki is the AI assistant embedded in Zervi's Odoo ERP. Its purpose is to reduce the time Zervi's team spends navigating Odoo — searching for records, performing repetitive actions, and looking up policies — by providing a conversational interface that understands context and can execute actions.

## Users

| User Type | Primary Need | Example |
|-----------|-------------|---------|
| Warehouse staff | Validate pickings, check stock | "Validate this transfer" |
| Sales | Confirm orders, check delivery | "Confirm and invoice this order" |
| Purchasing | Track POs, vendor status | "Show open purchase orders" |
| Manufacturing | Monitor production, check components | "Do I have all components for MO 42?" |
| Accounting | Review invoices, payments | "Show unpaid customer invoices" |
| Engineering | Find documents, manage revisions | "Find the pattern for product X" |
| HR | Employee records, leave | "Show Jo's leave balance" |
| Management (Archie) | Reports, approvals, overview | "What orders are overdue?" |

## Features

### Current (v0.3.1)
- Conversational chat with context awareness (active model, record, view)
- 18 executable tools (search, create, confirm, validate, post)
- 8 AI agents (1 default + 7 departmental specialists)
- RAG memory: conversation history, company documents, business facts
- Streaming responses (SSE)
- Proactive suggestions based on screen context
- File attachments (PDF, TXT, CSV, images)
- High-risk action confirmation gates
- Multi-language (English, Thai, Chinese)

### Planned (v0.4+)
- Agent auto-selection based on Odoo user role
- Brain sync from Odoo (single source of truth)
- Skill usage analytics
- Proactive alerts ("notify me when stock is low")
- Cross-module queries ("what's our margin on this order?")

## Non-Goals

- Saki does NOT replace Odoo's UI — it augments it
- Saki does NOT make decisions autonomously — high-risk actions require confirmation
- Saki does NOT give legal, tax, or compliance advice
- Saki does NOT store API keys or credentials (uses Infisical)

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Skills available | 18 | 30+ |
| Departmental agents | 7 | 7 (complete) |
| Response time (p95) | ~3s | <2s |
| User satisfaction | Not measured | >80% helpful feedback |
| Daily active users | Not measured | All Zervi staff |

## Dependencies

- DeepSeek API (LLM)
- OpenAI API (embeddings)
- PostgreSQL + pgvector (database)
- Elestio (hosting)
- Odoo ai_assistant_ui module (frontend)
- Infisical (secrets management)

## Related Documents

- `docs/tasks.md` — current tasks and blockers
- `docs/inventory.md` — environment and configuration
- `AGENTS.md` — rules for AI agents working on this repo
- `CHANGELOG.md` — version history

# AI Brain — Current Tasks & Focus

**Updated:** 2026-07-20
**Active focus:** Agent discoverability — wire departmental agents to Odoo UI, fix default agent awareness

## Current Phase

Phase 1 hardening — documentation, agent↔skill linking, system prompt fixes. Preparing for v2 agent/skill management in Odoo.

## Active Tasks

| # | Task | Status | Owner |
|---|------|--------|-------|
| 1 | Fix default agent system prompt (list departmental agents) | ✅ PR #36 | Zak |
| 2 | Add AGENTS.md, README.md, docs/ to brain repo | 🔧 In progress | Zak |
| 3 | Brain sync from Odoo (agents managed in Odoo, synced to brain) | ⏳ Pending | Zak |
| 4 | Add agent↔role group mapping (auto-select agent per Odoo user) | ⏳ Pending | Zak |
| 5 | Enhanced `/agents/{id}` endpoint with UI-ready skill cards | ⏳ Pending | Zak |
| 6 | Audit RAG cross-user boundary (ensure user_id isolation) | ⏳ Pending | Zak |
| 7 | Add endpoint for skill usage tracking | ⏳ Pending | Zak |

## Completed

| # | Task | Status |
|---|------|--------|
| — | Default agent prompt updated with departmental agent list | ✅ |
| — | 7 departmental agents with system prompts + skill groups | ✅ |
| — | 18 tools, RAG with 8 documents + 15 facts | ✅ |
| — | Streaming chat, suggestions, analyze endpoints | ✅ |
| — | DeepSeek retry/backoff, rate limiting | ✅ |
| — | File attachment processing | ✅ |

## Blockers

- Brain main branch requires PR — can't push directly
- Agent↔Odoo role mapping needs Odoo module changes (v2 spec)

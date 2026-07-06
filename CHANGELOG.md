# Changelog

All notable changes to the Saki AI Brain (FastAPI service) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `/chat/stream` endpoint for Server-Sent Events (SSE) token-by-token replies.
- `AGENTS.md` with repo-specific build, test, deploy, and rollback guidance.

### Changed
- Suggest prompt now asks the model to mention specific record names/reference numbers when they are visible.
- Default DeepSeek model aligned to `deepseek-v4-pro` in `docker-compose.prod.yml` and `.env.example`.

### Fixed
- `/documents` endpoint now passes the `offset` query parameter through to the database instead of hardcoding `0`.
- `/chat/stream` emits an immediate SSE comment keep-alive so browsers/proxies don't drop the connection before DeepSeek returns the first token.
- Reduced chat history context from 50 to 10 recent messages to lower prompt size and improve response latency.

## [1.0.0] - 2026-07-03

### Added
- Initial FastAPI brain service for Saki.
- `/chat` endpoint with DeepSeek integration.
- `/suggest` endpoint for proactive next-action suggestions.
- `/agents` and `/skills` endpoints for departmental agent management.
- RAG memory system with vector embeddings and knowledge retrieval.
- Tool execution framework with schemas for Odoo actions.

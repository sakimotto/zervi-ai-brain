# Changelog

All notable changes to the Saki AI Brain (FastAPI service) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `metadata_json` column on `facts` table with Alembic migration, plus `metadata` field on `FactCreate`/`FactOut` schemas. Enables the Odoo feedback loop to attach traceability metadata (message/chat IDs, active model/record) to user corrections.
- New `/chat/analyze` endpoint for one-shot, no-tools analysis of tool results (used by Odoo to turn raw search/count data into natural-language answers).

### Changed
- System prompt now includes `count_records` tool for aggregation/breakdown questions and instructs Saki to analyze tool results instead of echoing raw counts.

### Added
- `/chat/stream` endpoint for Server-Sent Events (SSE) token-by-token replies.
- Attachment support in `/chat` and `/chat/stream`:
  - `Attachment` schema and `attachments` field on `ChatRequest`.
  - Downloads files from Odoo `/web/content` URLs, extracts text from TXT/CSV/PDF,
    and encodes images as base64 data URLs for vision-capable models.
  - Injects extracted attachment content into the LLM prompt and system context.
  - Added `pypdf` dependency and unit tests for text, PDF, image, and unsupported
    attachments plus size-limit and download-failure handling.

### Changed
- Suggest prompt now asks the model to mention specific record names/reference numbers when they are visible.

## [1.0.0] - 2026-07-03

### Added
- Initial FastAPI brain service for Saki.
- `/chat` endpoint with DeepSeek integration.
- `/suggest` endpoint for proactive next-action suggestions.
- `/agents` and `/skills` endpoints for departmental agent management.
- RAG memory system with vector embeddings and knowledge retrieval.
- Tool execution framework with schemas for Odoo actions.

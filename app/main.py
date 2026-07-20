"""Zervi AI Brain — Phase 1: persistent memory, agents, skills, semantic search."""

import asyncio
import json
import logging
import os
import re
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from . import attachments, crud, schemas

logger = logging.getLogger(__name__)

from . import config
from .config import (
    AI_ASSISTANT_SECRET,
    ALLOWED_ORIGINS,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)
from .db import AsyncSessionLocal, engine, get_db
from .rate_limit import check_chat_rate_limit, check_suggest_rate_limit


# ------------------------------------------------------------------
# System prompt (seeded into the default DB agent on first start)
# ------------------------------------------------------------------
_DEFAULT_SYSTEM_PROMPT = (
    "You are Saki, the embedded AI assistant for the Zervi Odoo ERP system. You are cautious, highly analytical, "
    "and deeply knowledgeable about Zervi's operations (textile manufacturing, PUR lamination, neoprene, "
    "4x4 accessories, and global supply chain).\n\n"
    "### 0. DEPARTMENTAL AGENTS\n"
    "Zervi has seven specialist agents you can switch to for domain-specific help:\n"
    "- Sales Agent — quotations, orders, customers, invoices\n"
    "- Purchasing Agent — RFQs, purchase orders, vendors, receipts\n"
    "- Accounting Agent — invoices, payments, reconciliation, journal entries\n"
    "- Warehouse Agent — pickings, stock levels, transfers, backorders\n"
    "- Manufacturing Agent — MOs, BOMs, work orders, component availability\n"
    "- Engineering Agent — patterns, CAD, drawings, revisions, BOM linking\n"
    "- HR Agent — employees, contracts, leave, timesheets\n\n"
    "The user can switch agents using the dropdown at the top of the chat panel. "
    "When the user selects a specialist agent, that agent's expertise and tools become active. "
    "You are the Default Agent — you have access to ALL tools across all domains. "
    "If a user asks a purchasing question while the Default Agent is active, answer it. "
    "Suggest switching to the specialist agent if the conversation becomes domain-heavy.\n\n"
    "Your job is to help users understand records, answer questions from the provided context, suggest safe next steps, "
    "and perform actions ONLY when explicitly requested.\n\n"
    "### 1. CONTEXT AWARENESS\n"
    "You can see the user's current screen context (active model, record ID/res_id, view type, language), "
    "the readable fields of the record, summaries of its line items, and relevant past conversation snippets. "
    "Today's date is provided as `current_date`.\n"
    "- The context also includes `system_info` with `odoo_version`, `installed_module_count`, `database_name`, "
    "`active_company`, and the current `user`. Use these fields to answer administrative questions such as "
    "'How many modules are installed?' or 'What Odoo version is this?'.\n"
    "- If the context includes `visible_records`, use them to answer questions about the list (e.g., counts, summaries, which records are done). "
    "Respect `selected_ids` when the user refers to 'these records' or asks to act on the current selection.\n"
    "- Always check the `state` / `stage_id` fields of the provided records before suggesting actions. Never suggest confirming an already confirmed order, "
    "or validating an already completed picking.\n"
    "- If the context includes `selected_ids` and the user refers to 'these records', use those IDs. Never guess IDs.\n"
    "- The user can attach files (text, CSV, PDF, images). When files are provided, their content or a description "
    "is included in the conversation. Use the content to answer questions about the files.\n\n"
    "### 2. STRICT GUARD RAILS (Follow Exactly)\n"
    "- Zero Hallucination: Only state facts present in the provided context or conversation history. "
    'If data is missing, say: "I cannot see that information in the current record."\n'
    "- High-Stakes Boundary: For financial, legal, tax, or compliance questions, give general guidance only and instruct the user "
    "to verify with a human expert or official record.\n"
    "- Destructive Actions: NEVER suggest or execute deleting records, changing unit costs, altering landed costs, "
    "bypassing approvals, or overriding security settings.\n"
    "- UI Confirmation Reliance: The frontend UI will handle the final Confirm/Cancel step for high-risk actions. "
    "Your job is to output the correct JSON and provide a clear `confirmation_message` so the user knows exactly what they are approving.\n"
    "- Uncertainty: If you are unsure, say so rather than guessing.\n\n"
    "### 3. LANGUAGE & TERMINOLOGY\n"
    "- Dynamically match the language the user is typing in (English, Thai, or Chinese). If they ask in Thai, answer in Thai.\n"
    "- Understand Zervi manufacturing shorthand: PUR (polyurethane reactive), BOM (Bill of Materials), GSM (grams per square meter), "
    "routing, work centers, and neoprene/foam specifications.\n\n"
    "### 4. OUTPUT FORMAT (CRITICAL)\n"
    "You must strictly separate conversational answers from tool executions.\n\n"
    "Mode A: QUESTIONS, SUMMARIES, and CHAT\n"
    "- When the user asks about a record, page, task, order, or visible data, give a structured, useful summary. "
    "Use markdown headings ('## Section'), bullet points ('- **Label:** value'), and markdown tables for structured comparisons. "
    "Include relevant IDs, states, dates, amounts, and related records when they are in the context.\n"
    "- When you reference a specific record whose ID is in the provided context, make it clickable with `[Display Text](action:model/res_id)`.\n"
    "- For simple greetings or yes/no questions, keep the answer short. For record/page/task summaries, be thorough but organised.\n"
    "- **NEVER include raw JSON or tool schemas in Mode A.** If you are not executing an action, do not output JSON.\n"
    "- Address the user by their first name when it is provided in the context (`user_name`).\n"
    "- End record summaries with 1-3 concrete next actions or questions the user can follow up with.\n\n"
    "Mode B: EXPLICIT ACTION EXECUTION\n"
    "- ONLY use this mode when the user has explicitly commanded an action.\n"
    "- Output ONLY raw JSON. No markdown formatting (no ```json), no introductory text, no explanations, no trailing prose.\n"
    "- Use one of the two exact formats below.\n"
    "- For a single action, return a JSON object:\n"
    '   {"tool": "<tool_name>", "params": {<parameters>}}\n'
    "- For multiple related searches/lookups at once, return a JSON array of objects:\n"
    '   [{"tool": "search_records", "params": {...}}, {"tool": "get_coa_summary", "params": {...}}]\n'
    "- When returning an array, the first valid/allowed tool will be executed first. The rest should be related lookups the user asked for.\n"
    "- After emitting the JSON, stop. Do not add a conversational follow-up in the same message.\n"
    "- Use the exact schema defined below.\n\n"
    "### 5. AVAILABLE TOOLS & EXACT JSON SCHEMAS\n"
    "Only use these tools. Use the exact parameter names provided. "
    "If the user asks for data not present in the provided context, prefer the `search_records` tool to query Odoo directly.\n\n"
    "1. search_records (Read-only data lookup)\n"
    '   {"tool": "search_records", "params": {"res_model": "<model_name>", "domain": [["field", "operator", "value"], ...], "fields": ["field1", "field2", ...], "limit": 50}}\n'
    "   - domain values must be valid JSON: strings in quotes, booleans as true/false, numbers as numbers, null as null.\n"
    "   - Examples:\n"
    '     domain: [["type", "=", "product"], ["sale_ok", "=", true]]\n'
    '     domain: [["state", "in", ["confirmed", "progress"]]]\n'
    '     domain: [["code", "=like", "113%"]]\n'
    "   - Use this to answer questions like 'Show me all 113* accounts' (res_model: \"account.account\", domain: [[\"code\", \"=like\", \"113%\"]]).\n"
    "   - Do not guess record IDs; always search or use the IDs in the provided context.\n\n"
    "2. count_records (Read-only counts and group-by)\n"
    '   {"tool": "count_records", "params": {"res_model": "<model_name>", "domain": [["field", "operator", "value"], ...], "groupby": "<field_name>", "limit": 100}}\n'
    "   - Use this for 'how many', 'count', 'number of', or breakdown questions.\n"
    "   - Examples:\n"
    '     count product.template grouped by categ_id to answer "how many products per category?"\n'
    '     count sale.order with domain [["state","=","sale"]] to answer "how many confirmed orders?"\n'
    "   - If the user asks for a count while a list is filtered, include the same domain/filter in the count.\n\n"
    "3. create_activity (Low risk)\n"
    '   {"tool": "create_activity", "params": {"res_model": "<model_name>", "res_id": <integer>, "summary": "<string>", "note": "<string>", "date_deadline": "YYYY-MM-DD"}}\n\n'
    "4. post_chatter_message (Low risk)\n"
    '   {"tool": "post_chatter_message", "params": {"res_model": "<model_name>", "res_id": <integer>, "message": "<string>", "message_type": "comment|note"}}\n\n'
    "5. confirm_sales_order (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "confirm_sales_order", "params": {"res_model": "sale.order", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "6. validate_picking (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "validate_picking", "params": {"res_model": "stock.picking", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "7. done_manufacturing_order (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "done_manufacturing_order", "params": {"res_model": "mrp.production", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "8. confirm_purchase_order (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "confirm_purchase_order", "params": {"res_model": "purchase.order", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "9. create_invoice (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "create_invoice", "params": {"res_model": "sale.order", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "10. get_coa_summary (Read-only accounting lookup)\n"
    '   {"tool": "get_coa_summary", "params": {"prefix": "<code_prefix>"}}\n'
    "   - Use this to answer questions about the chart of accounts, e.g. inventory asset accounts (prefix '113'), expense accounts (prefix '5').\n\n"
    "11. get_inventory_valuation_setup (Read-only inventory lookup)\n"
    '   {"tool": "get_inventory_valuation_setup", "params": {}}\n'
    "   - Use this to answer 'What cost method do we use?' or 'How is inventory valued?'.\n\n"
    "12. search_engineering_documents (Read-only engineering document lookup)\n"
    '   {"tool": "search_engineering_documents", "params": {"code": "<partial_code>", "doc_type": "pattern|cad|drawing|fitting_instruction|cnc_file|spec|other", "product_id": <integer>, "bom_id": <integer>, "state": "draft|review|approved|released|obsolete", "limit": 20}}\n'
    "   - Use this when the user asks about patterns, CAD files, drawings, fitting instructions, CNC cut files, or engineering specs.\n\n"
    "13. list_open_engineering_tasks (Read-only engineering task lookup)\n"
    '   {"tool": "list_open_engineering_tasks", "params": {"project_id": <integer>, "task_subtype": "pattern_dev|cad_dev|sewing_drawing|fitting_instruction|cnc_file|revision|sample|test|other", "limit": 20}}\n'
    "   - Use this when the user asks about open engineering tasks, pattern development status, CAD work, or R&D tasks.\n\n"
    "14. create_engineering_project (Write - UI will show confirmation card)\n"
    '   {"tool": "create_engineering_project", "params": {"name": "<project_name>", "zervi_eng_type": "rnd|pattern|cad|sample|npi|other", "zervi_product_line": "seat_cover|tent|garment|fitness|other", "zervi_target_product_id": <integer>}}\n'
    "   - Use this when the user asks to start a new R&D project, pattern project, CAD project, or engineering project.\n\n"
    "15. add_engineering_task (Write - UI will show confirmation card)\n"
    '   {"tool": "add_engineering_task", "params": {"project_id": <integer>, "name": "<task_name>", "zervi_task_subtype": "pattern_dev|cad_dev|sewing_drawing|fitting_instruction|cnc_file|revision|sample|test|other", "zervi_deliverable_type": "file|drawing|bom_update|sample|report|none", "zervi_bom_id": <integer>}}\n'
    "   - Use this when the user asks to add a pattern task, CAD task, drawing task, fitting instruction task, CNC task, etc.\n\n"
    "16. link_bom_to_project (Write - UI will show confirmation card)\n"
    '   {"tool": "link_bom_to_project", "params": {"project_id": <integer>, "bom_id": <integer>}}\n'
    "   - Use this when the user asks to attach, link, or associate a BOM with an engineering project.\n\n"
    "17. create_engineering_document (Write - UI will show confirmation card)\n"
    '   {"tool": "create_engineering_document", "params": {"name": "<document_title>", "doc_type": "pattern|cad|drawing|fitting_instruction|cnc_file|spec|other", "code": "<optional_code>", "project_id": <integer>, "task_id": <integer>, "product_id": <integer>, "bom_id": <integer>}}\n'
    "   - Use this when the user asks to create/register a new engineering document.\n\n"
    "18. create_engineering_document_revision (Write - UI will show confirmation card)\n"
    '   {"tool": "create_engineering_document_revision", "params": {"document_id": <integer>, "name": "<revision_name>", "change_note": "<changes>", "attachment_id": <integer>, "attachment_filename": "<filename>", "attachment_data": "<base64>", "state": "draft|review|approved|released|obsolete"}}\n'
    "   - Use this when the user asks to add a revision, upload a file to a document, or release a new version. Provide either attachment_id OR attachment_filename + attachment_data.\n\n"
    "When a tool returns data (especially search_records or count_records), do not just echo the raw count or list. "
    "Analyze the result and answer the user's original question in a helpful way, using markdown tables or bullets when appropriate. "
    "For count_records group-by results, present the breakdown clearly. "
    "If the data does not answer the question, say so and offer a follow-up search.\n\n"
    "For actions on multiple selected records, replace `res_id` with `res_ids` (array of integers) and set res_model accordingly.\n\n"
    "If the user's intent is genuinely unclear, ask for clarification in one concise sentence. Interpret obvious typos and shorthand."
)

_SUGGEST_PROMPT = (
    "\n\n"
    "Proactive suggestion mode — you are looking at the user's current screen. "
    "Recommend the single most useful next action they could take. "
    "If specific records are visible and you can suggest a concrete next step, mention their names or reference numbers. "
    "If no record details are visible, still base your recommendation on the model type if one is provided. "
    "Be concise but specific (one short sentence).\n\n"
    "You must respond with ONLY a JSON object in this exact format:\n"
    '{"suggestion": "short recommendation text", "tool_request": null}\n\n'
    "If the recommendation maps to one of the available actions, include a tool_request using res_model, res_id, and confirmation_message for high-risk actions:\n"
    '{"suggestion": "Confirm this quotation to reserve stock", "tool_request": {"tool": "confirm_sales_order", "params": {"res_model": "sale.order", "res_id": 123, "confirmation_message": "Confirm Sales Order S0012?"}}}\n\n'
    "Do not include any prose outside the JSON object."
)

# Fallback suggestions when the LLM returns empty text. Prefer model-aware
# text so the assistant still feels context-sensitive.
_SUGGESTION_FALLBACKS = {
    "sale.order": "Review this sales order and confirm or invoice it when ready.",
    "purchase.order": "Check this purchase order status or confirm it with the vendor.",
    "account.move": "Review this invoice, register a payment, or send a reminder.",
    "stock.picking": "Validate this transfer or check availability and related orders.",
    "mrp.production": "Check component availability or mark this manufacturing order done.",
    "project.task": "Update this task status, log time, or create a follow-up activity.",
    "crm.lead": "Move this lead forward, schedule an activity, or draft a proposal.",
    "hr.employee": "Review this employee's contract, leave balance, or timesheet.",
    "product.product": "Check stock levels, sales history, or supplier costs for this product.",
    "res.partner": "Review this partner's open orders, invoices, or contact details.",
}


def _suggestion_fallback(context: Optional[Dict[str, Any]]) -> str:
    """Return a context-aware fallback when the model gives no suggestion."""
    model = (context or {}).get("active_model", "")
    if model:
        return _SUGGESTION_FALLBACKS.get(
            model,
            f"Ask me anything about this {model.split('.')[-1].replace('_', ' ')} record.",
        )
    return "Ask me anything about your orders, inventory, manufacturing, or accounting."


openai_client: Optional[AsyncOpenAI] = None
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


# ------------------------------------------------------------------
# LLM output budget
# ------------------------------------------------------------------
# DeepSeek v4-pro has a huge context window. For an ERP assistant, truncated
# replies (especially JSON tool calls) are far more expensive than tokens.
_MAX_TOKENS_CHAT = int(os.getenv("MAX_TOKENS_CHAT", "4096"))
_MAX_TOKENS_SUGGEST = int(os.getenv("MAX_TOKENS_SUGGEST", "512"))


# ------------------------------------------------------------------
# DeepSeek retry helpers
# ------------------------------------------------------------------
_DEEPSEEK_RETRYABLE_STATUS = {502, 503, 504, 429}
_DEEPSEEK_RETRY_ATTEMPTS = int(os.getenv("DEEPSEEK_RETRY_ATTEMPTS", "3"))
_DEEPSEEK_RETRY_BACKOFF = float(os.getenv("DEEPSEEK_RETRY_BACKOFF", "1.0"))


def _is_retryable_deepseek_error(exc: Exception) -> bool:
    """Return True for transient DeepSeek errors that are worth retrying."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _DEEPSEEK_RETRYABLE_STATUS
    return False


async def _deepseek_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    json_payload: Dict[str, Any],
    timeout: float,
) -> httpx.Response:
    """POST to DeepSeek with exponential backoff on transient errors."""
    last_exception: Optional[Exception] = None
    for attempt in range(_DEEPSEEK_RETRY_ATTEMPTS):
        try:
            response = await client.post(url, headers=headers, json=json_payload, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exception = exc
            if not _is_retryable_deepseek_error(exc):
                break
            if attempt < _DEEPSEEK_RETRY_ATTEMPTS - 1:
                wait = _DEEPSEEK_RETRY_BACKOFF * (2 ** attempt)
                logger.warning(
                    "DeepSeek POST failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    _DEEPSEEK_RETRY_ATTEMPTS,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
    raise last_exception


@asynccontextmanager
async def _deepseek_stream_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    json_payload: Dict[str, Any],
    timeout: float,
) -> AsyncGenerator[httpx.Response, None]:
    """Stream from DeepSeek with exponential backoff on transient connection errors."""
    last_exception: Optional[Exception] = None
    for attempt in range(_DEEPSEEK_RETRY_ATTEMPTS):
        try:
            async with client.stream("POST", url, headers=headers, json=json_payload, timeout=timeout) as response:
                response.raise_for_status()
                yield response
                return
        except Exception as exc:
            last_exception = exc
            if not _is_retryable_deepseek_error(exc):
                break
            if attempt < _DEEPSEEK_RETRY_ATTEMPTS - 1:
                wait = _DEEPSEEK_RETRY_BACKOFF * (2 ** attempt)
                logger.warning(
                    "DeepSeek stream failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    _DEEPSEEK_RETRY_ATTEMPTS,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
    raise last_exception


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _extract_json(text: str) -> Optional[Any]:
    """Try to extract a JSON object/array from a string, even inside markdown.

    Strategy:
      1. Strip markdown fences and try the whole string as JSON.
      2. Look for the first {...} block that parses as a valid dict.
         For tool requests, require both 'tool' and 'params' keys so
         conversational text with braces does not collide.
      3. Look for the first [...] block that parses as a valid list of
         tool-shaped dicts (each contains 'tool' and 'params').
      4. Otherwise return None.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Whole string may already be JSON.
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            if "tool" in parsed and "params" in parsed:
                return parsed
            # Whole string is a non-tool dict; do not treat as a tool request.
            return None
        if isinstance(parsed, list) and all(
            isinstance(item, dict) and "tool" in item and "params" in item
            for item in parsed
        ):
            return parsed
        return None
    except json.JSONDecodeError:
        pass

    # Fallback 1: find the first {...} block that parses as a tool request.
    for match in re.finditer(r"\{.*\}", cleaned, re.DOTALL):
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict) and "tool" in parsed and "params" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    # Fallback 2: find the first [...] block that parses as a list of tools.
    for match in re.finditer(r"\[.*\]", cleaned, re.DOTALL):
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and all(
                isinstance(item, dict) and "tool" in item and "params" in item
                for item in parsed
            ):
                return parsed
        except json.JSONDecodeError:
            continue

    return None


def _parse_reply(text: str) -> Dict[str, Any]:
    """Parse a chat reply.

    Supports:
      - Plain text replies.
      - A single tool request: {"tool": "...", "params": {...}}
      - Multiple tool requests: [{"tool": "...", "params": {...}}, ...]

    When multiple tool requests are returned, only the first allowed/valid one
    is exposed for execution. The others are preserved in the raw text so the
    frontend can display what Saki intended to do.
    """
    data = _extract_json(text)
    if isinstance(data, dict) and "tool" in data and "params" in data:
        return {"tool_request": data, "multi_tool_requests": None}
    if isinstance(data, list):
        valid_tools = [
            item for item in data
            if isinstance(item, dict) and "tool" in item and "params" in item
        ]
        if valid_tools:
            return {
                "tool_request": valid_tools[0],
                "multi_tool_requests": valid_tools,
            }
    return {"reply": text.strip(), "tool_request": None, "multi_tool_requests": None}


def _parse_suggestion(text: str) -> Dict[str, Any]:
    """Parse a suggestion reply, supporting markdown-fenced JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {"suggestion": text.strip()[:500], "tool_request": None}

    if isinstance(data, dict) and "suggestion" in data:
        tool_request = data.get("tool_request")
        if tool_request and not isinstance(tool_request, dict):
            tool_request = None
        if tool_request and ("tool" not in tool_request or "params" not in tool_request):
            tool_request = None
        return {"suggestion": str(data["suggestion"]), "tool_request": tool_request}

    return {"suggestion": text.strip()[:500], "tool_request": None}


def _tool_allowed_by_schemas(tool_name: str, skill_schemas: List[List[Dict[str, Any]]]) -> bool:
    """Return True if the requested tool name exists in the skill schemas.

    Supports both legacy schemas keyed by 'name' and current schemas keyed by 'tool'.
    """
    for schemas in skill_schemas:
        for schema in schemas:
            if schema.get("name") == tool_name or schema.get("tool") == tool_name:
                return True
    return False


def _tool_allowed_for_agent(tool_name: str, agent) -> bool:
    """Return True if the requested tool name exists in one of the agent's skills."""
    if not agent or not hasattr(agent, "skills"):
        return False
    skill_schemas = [skill.tool_schemas_json or [] for skill in agent.skills]
    return _tool_allowed_by_schemas(tool_name, skill_schemas)


def _validate_tool_request(
    tool_request: Dict[str, Any],
    agent_or_schemas: Any,
) -> Optional[Dict[str, Any]]:
    """Validate and return a tool request only if it is allowed for the agent."""
    if not isinstance(tool_request, dict):
        return None
    tool_name = tool_request.get("tool")
    params = tool_request.get("params")
    if not tool_name or not isinstance(params, dict):
        return None
    if hasattr(agent_or_schemas, "skills"):
        allowed = _tool_allowed_for_agent(tool_name, agent_or_schemas)
    elif isinstance(agent_or_schemas, list):
        allowed = _tool_allowed_by_schemas(tool_name, agent_or_schemas)
    else:
        allowed = False
    if not allowed:
        return None
    return {"tool": tool_name, "params": params}


async def _embed_text(text: str) -> Optional[List[float]]:
    if not openai_client:
        return None
    try:
        response = await openai_client.embeddings.create(
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            input=text,
        )
        return response.data[0].embedding
    except Exception:
        return None


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """Split long text into overlapping chunks for embedding."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


async def _retrieve_knowledge(
    db: AsyncSession, user_id: int, query: str, message_id_to_skip: Any = None
) -> Dict[str, Any]:
    """Retrieve relevant past messages, documents, and facts for a query."""
    snippets: List[str] = []
    sources: List[Dict[str, Any]] = []
    embedding = await _embed_text(query)
    if not embedding:
        return {"snippets": snippets, "sources": sources}

    # Past messages
    similar_messages = await crud.search_similar_messages(db, user_id, embedding, limit=5)
    for msg, distance in similar_messages:
        if message_id_to_skip and msg.id == message_id_to_skip:
            continue
        if distance is not None and distance < config.SIMILARITY_THRESHOLD:
            snippets.append(f"Past conversation - {msg.role}: {msg.content}")

    # Documents
    similar_docs = await crud.search_similar_documents(db, embedding, limit=10)
    seen_doc_groups = set()
    for doc, distance in similar_docs:
        if distance is not None and distance < config.SIMILARITY_THRESHOLD:
            snippets.append(f"Document [{doc.source}] {doc.title}:\n{doc.content}")
            group_id = (doc.metadata_json or {}).get("group_id")
            dedupe_key = group_id or str(doc.id)
            if dedupe_key not in seen_doc_groups:
                seen_doc_groups.add(dedupe_key)
                sources.append(
                    {
                        "type": "document",
                        "source": doc.source,
                        "title": doc.title,
                        "distance": distance,
                    }
                )

    # Facts
    similar_facts = await crud.search_similar_facts(db, user_id, embedding, limit=5)
    for fact, distance in similar_facts:
        if distance is not None and distance < config.SIMILARITY_THRESHOLD:
            snippets.append(f"Known fact ({fact.category}) - {fact.key}: {fact.value}")
            sources.append(
                {
                    "type": "fact",
                    "category": fact.category,
                    "key": fact.key,
                    "distance": distance,
                }
            )

    return {"snippets": snippets, "sources": sources}


def _build_context_message(context: Dict[str, Any]) -> Dict[str, str]:
    ctx = context or {}
    user_name = ctx.get("user_name") or (ctx.get("user") or {}).get("name")
    if user_name:
        greeting = f"The current user's first name is {user_name}. Address them by this name.\n\n"
    else:
        greeting = ""
    # Serialize context as pretty JSON inside a fenced block so model output
    # in context values cannot break out of the system instructions.
    try:
        context_json = json.dumps(ctx, ensure_ascii=False, default=str, indent=2)
    except (TypeError, ValueError):
        context_json = str(ctx)
    return {
        "role": "system",
        "content": greeting + "Current Odoo context (JSON):\n```json\n" + context_json + "\n```",
    }


async def _build_attachment_context_message(
    attachment_dicts: List[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    """Build a system message describing attached files and extracted text."""
    context_text = await attachments.build_attachment_context(attachment_dicts)
    if not context_text:
        return None
    return {"role": "system", "content": context_text}


def _quote_for_prompt(text: str, max_length: int = 500) -> str:
    """Quote a user-supplied string so it cannot escape system instructions."""
    text = text or ""
    # Strip delimiter sequences that could close the quoting block.
    text = text.replace('"""', '').replace("```", "")
    return text[:max_length]


async def _run_alembic_upgrade() -> None:
    """Run pending DB migrations in a subprocess to avoid async loop issues."""
    project_root = Path(__file__).resolve().parent.parent
    proc = await asyncio.create_subprocess_exec(
        "alembic",
        "upgrade",
        "head",
        cwd=str(project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"Alembic upgrade failed ({proc.returncode}): {stderr.decode() or stdout.decode()}"
        )


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run any pending DB migrations on startup.
    try:
        await _run_alembic_upgrade()
    except Exception as exc:
        # Migrations may fail if the DB is temporarily unreachable. Log and
        # continue; the health endpoint will report the real DB status.
        logger.warning("Database migrations could not run: %s", exc)

    # Seed the default agent + skills + department knowledge on startup.
    async with AsyncSessionLocal() as db:
        try:
            await crud.ensure_default_agent_and_skills(db, _DEFAULT_SYSTEM_PROMPT)
            await crud.ensure_department_knowledge(db, _embed_text)
        except SQLAlchemyError:
            # If the DB is not yet migrated, seeding will fail. The app still
            # starts so that health checks and migration tooling work.
            pass
    yield


app = FastAPI(title="Zervi AI Brain", version="0.3.1", lifespan=lifespan)

# Allow the configured Odoo frontend(s) to call the brain from the browser.
# In production, AI_ASSISTANT_SECRET is still required for every endpoint.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with a request ID, duration, and status code."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "method=%s path=%s status=%s duration_ms=%.2f request_id=%s client=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
        request.client.host if request.client else None,
    )
    return response


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
def _check_secret(x_secret: Optional[str]) -> None:
    if not AI_ASSISTANT_SECRET:
        raise HTTPException(status_code=500, detail="AI assistant secret is not configured")
    if x_secret != AI_ASSISTANT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")


@app.post("/chat", response_model=schemas.ChatResponse)
async def chat(
    req: schemas.ChatRequest,
    request: Request,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.ChatResponse:
    _check_secret(x_ai_assistant_secret)
    await check_chat_rate_limit(request, req.user_id)

    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API key is not configured")

    try:
        agent = await crud.get_agent(db, req.agent_id)
        if not agent:
            agent = await crud.get_default_agent(db)
        if not agent:
            raise HTTPException(status_code=500, detail="No AI agent configured")

        # Resolve or create session.
        if req.session_id:
            session = await crud.get_session(db, req.session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        else:
            session = await crud.create_session(db, req.user_id, req.context)

        # Persist the user's message.
        user_message = await crud.add_message(
            db, str(session.id), "user", req.message, token_count=None
        )

        # Fetch recent history and relevant semantic memory.
        recent_db_messages = await crud.get_recent_messages(db, str(session.id), limit=50)
        recent_db_messages = list(reversed(recent_db_messages))  # chronological

        knowledge = await _retrieve_knowledge(db, req.user_id, req.message, message_id_to_skip=user_message.id)
        relevant_snippets = knowledge["snippets"]
        source_citations = knowledge["sources"]

        # Build LLM messages.
        recent_messages = [{"role": msg.role, "content": msg.content} for msg in recent_db_messages]
        skill_schemas = [skill.tool_schemas_json for skill in agent.skills]
        messages = await _build_llm_messages(
            agent.system_prompt,
            skill_schemas,
            req.context,
            recent_messages,
            relevant_snippets,
            req.message,
            [att.model_dump(by_alias=True) for att in req.attachments] if req.attachments else None,
        )

        # Call DeepSeek with retry on transient errors.
        async with httpx.AsyncClient() as client:
            response = await _deepseek_post_with_retry(
                client,
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json_payload={
                    "model": DEEPSEEK_MODEL,
                    "messages": messages,
                    "max_tokens": _MAX_TOKENS_CHAT,
                },
                timeout=60.0,
            )
        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"]
        parsed = _parse_reply(raw_reply)
        validated_tool_request = _validate_tool_request(parsed.get("tool_request"), agent)

        # Persist the assistant reply.
        assistant_content = parsed.get("reply") or json.dumps(validated_tool_request)
        assistant_message = await crud.add_message(
            db, str(session.id), "assistant", assistant_content, token_count=None
        )

        # Save embeddings for both messages.
        for text, msg_record in ((req.message, user_message), (assistant_content, assistant_message)):
            embedding = await _embed_text(text)
            if embedding:
                await crud.save_embedding(db, str(msg_record.id), embedding)

        return schemas.ChatResponse(
            reply=parsed.get("reply"),
            tool_request=validated_tool_request,
            session_id=str(session.id),
            sources=source_citations,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek API error: {exc.response.status_code} - {exc.response.text}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")


@app.post("/chat/analyze", response_model=schemas.AnalyzeResponse)
async def chat_analyze(
    req: schemas.AnalyzeRequest,
    request: Request,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.AnalyzeResponse:
    """One-shot analysis endpoint for tool results.

    Does not persist messages. Uses a no-tools system prompt so the LLM
    answers the provided prompt directly instead of emitting tool calls.
    """
    _check_secret(x_ai_assistant_secret)
    await check_chat_rate_limit(request, req.user_id)

    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API key is not configured")

    system_prompt = (
        "You are Saki, a helpful ERP assistant. Answer the user's prompt directly using the data provided. "
        "Do not call any tools. Use markdown tables or bullets when helpful. Be concise but specific."
    )

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.prompt},
        ]
        async with httpx.AsyncClient() as client:
            response = await _deepseek_post_with_retry(
                client,
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json_payload={
                    "model": DEEPSEEK_MODEL,
                    "messages": messages,
                    "max_tokens": _MAX_TOKENS_CHAT,
                },
                timeout=60.0,
            )
        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"]
        return schemas.AnalyzeResponse(reply=raw_reply.strip() or None)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek API error: {exc.response.status_code} - {exc.response.text}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")


async def _build_llm_messages(
    system_prompt: str,
    skill_schemas: List[List[Dict[str, Any]]],
    context: Dict[str, Any],
    recent_messages: List[Dict[str, str]],
    relevant_snippets: List[str],
    user_message: str,
    attachment_dicts: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Assemble the message list sent to the LLM."""
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    tool_schema_blocks: List[str] = []
    for schemas in skill_schemas:
        for schema in schemas:
            tool_schema_blocks.append(json.dumps(schema))
    if tool_schema_blocks:
        messages.append(
            {
                "role": "system",
                "content": "Available tool schemas:\n" + "\n".join(tool_schema_blocks),
            }
        )

    if context:
        messages.append(_build_context_message(context))

    if relevant_snippets:
        citation_instruction = (
            "\n\nWhen you use the retrieved information above, cite the source in your answer "
            "using a short tag like [doc:source:title] or [fact:category:key]."
        )
        messages.append(
            {
                "role": "system",
                "content": "Retrieved knowledge:\n" + "\n---\n".join(relevant_snippets) + citation_instruction,
            }
        )

    if attachment_dicts:
        attachment_context = await _build_attachment_context_message(attachment_dicts)
        if attachment_context:
            messages.append(attachment_context)

    messages.extend(recent_messages)

    if attachment_dicts:
        processed = await attachments.process_attachments(attachment_dicts)
        messages.append(attachments.build_user_message_with_attachments(user_message, processed))
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


# ------------------------------------------------------------------
# Streaming chat endpoint
# ------------------------------------------------------------------
async def _stream_chat(
    req: schemas.ChatRequest,
) -> AsyncGenerator[str, None]:
    """Internal generator that yields SSE events for a streaming chat reply.

    DB sessions are opened only for persistence work; the HTTP stream itself
    does not hold a database connection.
    """
    if not DEEPSEEK_API_KEY:
        yield _sse_event("error", "DeepSeek API key is not configured")
        return

    # ------------------------------------------------------------------
    # Phase 1: prepare context and persist the user's message.
    # ------------------------------------------------------------------
    async with AsyncSessionLocal() as db:
        agent = await crud.get_agent(db, req.agent_id)
        if not agent:
            agent = await crud.get_default_agent(db)
        if not agent:
            yield _sse_event("error", "No AI agent configured")
            return

        # Resolve or create session.
        if req.session_id:
            session = await crud.get_session(db, req.session_id)
            if not session:
                yield _sse_event("error", "Session not found")
                return
        else:
            session = await crud.create_session(db, req.user_id, req.context)

        session_id = str(session.id)

        # Persist the user's message.
        user_message = await crud.add_message(
            db, session_id, "user", req.message, token_count=None
        )
        user_message_id = str(user_message.id)

        # Fetch recent history and relevant semantic memory.
        recent_db_messages = await crud.get_recent_messages(db, session_id, limit=50)
        recent_db_messages = list(reversed(recent_db_messages))

        knowledge = await _retrieve_knowledge(
            db, req.user_id, req.message, message_id_to_skip=user_message.id
        )
        relevant_snippets = knowledge["snippets"]
        source_citations = knowledge["sources"]

        # Capture serializable state for the streaming phase.
        system_prompt = agent.system_prompt
        skill_schemas = [skill.tool_schemas_json or [] for skill in agent.skills]
        recent_messages = [{"role": msg.role, "content": msg.content} for msg in recent_db_messages]

    messages = await _build_llm_messages(
        system_prompt,
        skill_schemas,
        req.context,
        recent_messages,
        relevant_snippets,
        req.message,
        [att.model_dump(by_alias=True) for att in req.attachments] if req.attachments else None,
    )

    # ------------------------------------------------------------------
    # Phase 2: stream tokens from DeepSeek without holding a DB session.
    # ------------------------------------------------------------------
    full_reply = ""
    try:
        async with httpx.AsyncClient() as client:
            async with _deepseek_stream_with_retry(
                client,
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json_payload={
                    "model": DEEPSEEK_MODEL,
                    "messages": messages,
                    "max_tokens": _MAX_TOKENS_CHAT,
                    "stream": True,
                },
                timeout=60.0,
            ) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content") or ""
                    if token:
                        full_reply += token
                        yield _sse_event("token", token)
    except httpx.HTTPStatusError as exc:
        yield _sse_event("error", f"DeepSeek API error: {exc.response.status_code}")
        return
    except Exception as exc:
        yield _sse_event("error", f"Unexpected error: {exc}")
        return

    # ------------------------------------------------------------------
    # Phase 3: persist the assistant reply and embeddings.
    # ------------------------------------------------------------------
    parsed = _parse_reply(full_reply)
    validated_tool_request = _validate_tool_request(parsed.get("tool_request"), skill_schemas)
    assistant_content = parsed.get("reply") or json.dumps(validated_tool_request)

    async with AsyncSessionLocal() as db:
        assistant_message = await crud.add_message(
            db, session_id, "assistant", assistant_content, token_count=None
        )

        for text, msg_id in (
            (req.message, user_message_id),
            (assistant_content, str(assistant_message.id)),
        ):
            embedding = await _embed_text(text)
            if embedding:
                await crud.save_embedding(db, msg_id, embedding)

    if validated_tool_request:
        yield _sse_event("tool_request", json.dumps(validated_tool_request))
    else:
        yield _sse_event("reply", parsed.get("reply") or "")

    yield _sse_event("done", json.dumps({"session_id": session_id, "sources": source_citations}))


def _sse_event(event: str, data: str) -> str:
    """Build a valid SSE event, splitting multi-line data across data: lines."""
    lines = str(data).split("\n")
    payload = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event}\n{payload}\n\n"


@app.post("/chat/stream")
async def chat_stream(
    req: schemas.ChatRequest,
    request: Request,
    x_ai_assistant_secret: Optional[str] = Header(None),
) -> StreamingResponse:
    _check_secret(x_ai_assistant_secret)
    await check_chat_rate_limit(request, req.user_id)

    return StreamingResponse(
        _stream_chat(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/suggest", response_model=schemas.SuggestResponse)
async def suggest(
    req: schemas.SuggestRequest,
    request: Request,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.SuggestResponse:
    _check_secret(x_ai_assistant_secret)
    await check_suggest_rate_limit(request, req.user_id)

    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API key is not configured")

    try:
        agent = await crud.get_agent(db, req.agent_id)
        if not agent:
            agent = await crud.get_default_agent(db)
        if not agent:
            raise HTTPException(status_code=500, detail="No AI agent configured")

        system_content = agent.system_prompt + _SUGGEST_PROMPT
        if req.refresh:
            system_content += (
                "\n\nThe user has explicitly asked for a fresh suggestion. "
                "Recommend a different useful next action than before."
            )
        if req.last_suggestion:
            safe_last = _quote_for_prompt(req.last_suggestion)
            system_content += (
                f'\n\nPrevious suggestion (do not repeat it):\n"""{safe_last}"""'
            )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_content}
        ]

        if req.context:
            messages.append(_build_context_message(req.context))

        async with httpx.AsyncClient() as client:
            response = await _deepseek_post_with_retry(
                client,
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json_payload={
                    "model": DEEPSEEK_MODEL,
                    "messages": messages,
                    "max_tokens": _MAX_TOKENS_SUGGEST,
                    "temperature": 0.8 if req.refresh else 0.3,
                },
                timeout=60.0,
            )
        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"]
        parsed = _parse_suggestion(raw_reply)
        suggestion_text = (parsed.get("suggestion") or "").strip()
        if not suggestion_text:
            suggestion_text = _suggestion_fallback(req.context)
        skill_schemas = [skill.tool_schemas_json or [] for skill in agent.skills]
        validated_tool_request = _validate_tool_request(parsed.get("tool_request"), skill_schemas)
        return schemas.SuggestResponse(
            suggestion=suggestion_text,
            tool_request=validated_tool_request,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek API error: {exc.response.status_code} - {exc.response.text}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")


@app.get("/agents", response_model=List[schemas.AgentOut])
async def list_agents(
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.AgentOut]:
    _check_secret(x_ai_assistant_secret)
    agents = await crud.get_agents(db, active_only=True)
    return [schemas.AgentOut.model_validate(a) for a in agents]


@app.post("/agents", response_model=schemas.AgentOut)
async def create_agent(
    req: schemas.AgentCreate,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.AgentOut:
    _check_secret(x_ai_assistant_secret)
    agent = await crud.create_agent(
        db,
        name=req.name,
        system_prompt=req.system_prompt,
        is_active=req.is_active,
        skill_ids=req.skill_ids,
    )
    return schemas.AgentOut.model_validate(agent)


@app.get("/agents/{agent_id}", response_model=schemas.AgentOut)
async def get_agent_config(
    agent_id: int,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.AgentOut:
    _check_secret(x_ai_assistant_secret)
    agent = await crud.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return schemas.AgentOut.model_validate(agent)


@app.get("/sessions", response_model=List[schemas.SessionOut])
async def list_sessions(
    user_id: int,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.SessionOut]:
    _check_secret(x_ai_assistant_secret)
    sessions = await crud.get_sessions_for_user(db, user_id)
    return [schemas.SessionOut.model_validate(s) for s in sessions]


# ------------------------------------------------------------------
# Documents
# ------------------------------------------------------------------
@app.post("/documents", response_model=schemas.DocumentOut)
async def create_document(
    req: schemas.DocumentCreate,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.DocumentOut:
    _check_secret(x_ai_assistant_secret)
    chunks = _chunk_text(req.content)
    group_id = str(uuid.uuid4())

    # Embed chunks concurrently with a small concurrency limit.
    semaphore = asyncio.Semaphore(5)

    async def _embed_chunk(text: str) -> Optional[List[float]]:
        async with semaphore:
            return await _embed_text(text)

    embeddings = await asyncio.gather(*[_embed_chunk(chunk) for chunk in chunks])

    stored_docs = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        metadata = dict(req.metadata or {})
        metadata.update(
            {
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "group_id": group_id,
            }
        )
        doc = await crud.create_document(
            db,
            source=req.source,
            title=req.title,
            content=chunk,
            content_type=req.content_type,
            embedding=embedding,
            metadata=metadata,
        )
        stored_docs.append(doc)
    # Return the first chunk as the representative document.
    representative = stored_docs[0]
    return schemas.DocumentOut.model_validate(representative)


@app.get("/documents", response_model=List[schemas.DocumentOut])
async def list_documents(
    source: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.DocumentOut]:
    _check_secret(x_ai_assistant_secret)
    docs = await crud.list_documents(db, source=source, content_type=content_type, limit=limit * 4, offset=0)
    # Group chunk rows by their document group_id and return one representative per document.
    seen_groups = set()
    representatives = []
    for doc in docs:
        group_id = (doc.metadata_json or {}).get("group_id")
        if group_id:
            if group_id in seen_groups:
                continue
            seen_groups.add(group_id)
        representatives.append(doc)
        if len(representatives) >= limit:
            break
    return [schemas.DocumentOut.model_validate(d) for d in representatives]


@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _check_secret(x_ai_assistant_secret)
    deleted = await crud.delete_document(db, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


@app.delete("/documents/group/{group_id}")
async def delete_document_group(
    group_id: str,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _check_secret(x_ai_assistant_secret)
    deleted = await crud.delete_documents_by_group(db, group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document group not found")
    return {"deleted": True, "count": deleted}


# ------------------------------------------------------------------
# Facts
# ------------------------------------------------------------------
@app.post("/facts", response_model=schemas.FactOut)
async def create_fact(
    req: schemas.FactCreate,
    user_id: int,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.FactOut:
    _check_secret(x_ai_assistant_secret)
    embedding = await _embed_text(f"{req.category} {req.key} {req.value}")
    fact = await crud.create_fact(
        db,
        user_id=user_id,
        category=req.category,
        key=req.key,
        value=req.value,
        embedding=embedding,
        metadata=req.metadata,
    )
    return schemas.FactOut.model_validate(fact)


@app.get("/facts", response_model=List[schemas.FactOut])
async def list_facts(
    user_id: int,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.FactOut]:
    _check_secret(x_ai_assistant_secret)
    facts = await crud.list_facts(db, user_id=user_id, category=category, limit=limit, offset=offset)
    return [schemas.FactOut.model_validate(f) for f in facts]


@app.delete("/facts/{fact_id}")
async def delete_fact(
    fact_id: str,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    _check_secret(x_ai_assistant_secret)
    deleted = await crud.delete_fact(db, fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"deleted": True}

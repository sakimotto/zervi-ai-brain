"""Zervi AI Brain — Phase 1: persistent memory, agents, skills, semantic search."""

import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, schemas
from .config import (
    AI_ASSISTANT_SECRET,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)
from .db import AsyncSessionLocal, engine, get_db


# ------------------------------------------------------------------
# System prompt (seeded into the default DB agent on first start)
# ------------------------------------------------------------------
_DEFAULT_SYSTEM_PROMPT = (
    "You are Saki, the embedded AI assistant for the Zervi Odoo ERP system. You are cautious, highly analytical, "
    "and deeply knowledgeable about Zervi's operations (textile manufacturing, PUR lamination, neoprene, "
    "4x4 accessories, and global supply chain).\n\n"
    "Your job is to help users understand records, answer questions from the provided context, suggest safe next steps, "
    "and perform actions ONLY when explicitly requested.\n\n"
    "### 1. CONTEXT AWARENESS\n"
    "You can see the user's current screen context (active model, record ID/res_id, view type, language), "
    "the readable fields of the record, summaries of its line items, and relevant past conversation snippets. "
    "Today's date is provided as `current_date`.\n"
    "- If the context includes `visible_records`, use them to answer questions about the list (e.g., counts, summaries, which records are done). "
    "Respect `selected_ids` when the user refers to 'these records' or asks to act on the current selection.\n"
    "- Always check the `state` / `stage_id` fields of the provided records before suggesting actions. Never suggest confirming an already confirmed order, "
    "or validating an already completed picking.\n"
    "- If the context includes `selected_ids` and the user refers to 'these records', use those IDs. Never guess IDs.\n\n"
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
    "- Use markdown headings ('## Section'), bullet points ('- **Label:** value'), and markdown tables for structured comparisons.\n"
    "- When you reference a specific record whose ID is in the provided context, make it clickable with `[Display Text](action:model/res_id)`.\n"
    "- Keep answers concise and professional. No greetings, no fluff.\n\n"
    "Mode B: EXPLICIT ACTION EXECUTION\n"
    "- ONLY use this mode when the user has explicitly commanded an action.\n"
    "- Output ONLY a raw JSON object. No markdown formatting (no ```json), no introductory text, no explanations.\n"
    "- Use the exact schema defined below.\n\n"
    "### 5. AVAILABLE TOOLS & EXACT JSON SCHEMAS\n"
    "Only use these tools. Use the exact parameter names provided.\n\n"
    "1. create_activity (Low risk)\n"
    '   {"tool": "create_activity", "params": {"res_model": "<model_name>", "res_id": <integer>, "summary": "<string>", "note": "<string>", "date_deadline": "YYYY-MM-DD"}}\n\n'
    "2. post_chatter_message (Low risk)\n"
    '   {"tool": "post_chatter_message", "params": {"res_model": "<model_name>", "res_id": <integer>, "message": "<string>", "message_type": "comment|note"}}\n\n'
    "3. confirm_sales_order (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "confirm_sales_order", "params": {"res_model": "sale.order", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "4. validate_picking (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "validate_picking", "params": {"res_model": "stock.picking", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "5. done_manufacturing_order (HIGH RISK - UI will show confirmation card)\n"
    '   {"tool": "done_manufacturing_order", "params": {"res_model": "mrp.production", "res_id": <integer>, "confirmation_message": "<Explicit summary>"}}\n\n'
    "For actions on multiple selected records, replace `res_id` with `res_ids` (array of integers) and set res_model accordingly.\n\n"
    "If the user's intent is genuinely unclear, ask for clarification in one concise sentence. Interpret obvious typos and shorthand."
)

_SUGGEST_PROMPT = (
    "\n\n"
    "Proactive suggestion mode — you are looking at the user's current screen. "
    "Recommend the single most useful next action they could take on this record. "
    "Only recommend an action if it is clearly appropriate based on the visible record state. "
    "Be concise (one short sentence).\n\n"
    "You must respond with ONLY a JSON object in this exact format:\n"
    '{"suggestion": "short recommendation text", "tool_request": null}\n\n'
    "If the recommendation maps to one of the available actions, include a tool_request using res_model, res_id, and confirmation_message for high-risk actions:\n"
    '{"suggestion": "Confirm this quotation to reserve stock", "tool_request": {"tool": "confirm_sales_order", "params": {"res_model": "sale.order", "res_id": 123, "confirmation_message": "Confirm Sales Order S0012?"}}}\n\n'
    "Do not include any prose outside the JSON object."
)


openai_client: Optional[AsyncOpenAI] = None
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _parse_reply(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "tool" in data and "params" in data:
            return {"tool_request": data}
    except json.JSONDecodeError:
        pass
    return {"reply": text}


def _parse_suggestion(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "suggestion" in data:
            tool_request = data.get("tool_request")
            if tool_request and not isinstance(tool_request, dict):
                tool_request = None
            return {"suggestion": data["suggestion"], "tool_request": tool_request}
    except json.JSONDecodeError:
        pass
    return {"suggestion": cleaned[:500], "tool_request": None}


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
        if distance is not None and distance < 0.4:
            snippets.append(f"Past conversation - {msg.role}: {msg.content}")

    # Documents
    similar_docs = await crud.search_similar_documents(db, embedding, limit=5)
    for doc, distance in similar_docs:
        if distance is not None and distance < 0.4:
            snippets.append(f"Document [{doc.source}] {doc.title}:\n{doc.content}")
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
        if distance is not None and distance < 0.4:
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
    lines = [f"{k}: {v}" for k, v in ctx.items()]
    return {"role": "system", "content": "Current Odoo context:\n" + "\n".join(lines)}


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run any pending DB migrations on startup.
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        command.upgrade(alembic_cfg, "head")
    except Exception:
        # Migrations may fail if the DB is temporarily unreachable. Log and
        # continue; the health endpoint will report the real DB status.
        pass

    # Seed the default agent + skills on startup.
    async with AsyncSessionLocal() as db:
        try:
            await crud.ensure_default_agent_and_skills(db, _DEFAULT_SYSTEM_PROMPT)
        except SQLAlchemyError:
            # If the DB is not yet migrated, seeding will fail. The app still
            # starts so that health checks and migration tooling work.
            pass
    yield


app = FastAPI(title="Zervi AI Brain", version="0.3.0", lifespan=lifespan)

# Allow the Odoo frontend(s) to call the brain from the browser.
# In production, AI_ASSISTANT_SECRET is still required for every endpoint.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
def _check_secret(x_secret: Optional[str]) -> None:
    if AI_ASSISTANT_SECRET and x_secret != AI_ASSISTANT_SECRET:
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
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.ChatResponse:
    _check_secret(x_ai_assistant_secret)

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
        messages: List[Dict[str, str]] = [{"role": "system", "content": agent.system_prompt}]

        # Inject available tool schemas from the agent's skills.
        tool_schema_blocks: List[str] = []
        for skill in agent.skills:
            for schema in skill.tool_schemas_json:
                tool_schema_blocks.append(json.dumps(schema))
        if tool_schema_blocks:
            messages.append(
                {
                    "role": "system",
                    "content": "Available tool schemas:\n" + "\n".join(tool_schema_blocks),
                }
            )

        if req.context:
            messages.append(_build_context_message(req.context))

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

        for msg in recent_db_messages:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": req.message})

        # Call DeepSeek.
        response = await httpx.AsyncClient().post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "max_tokens": 1024,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"]
        parsed = _parse_reply(raw_reply)

        # Persist the assistant reply.
        assistant_content = parsed.get("reply") or json.dumps(parsed.get("tool_request"))
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
            tool_request=parsed.get("tool_request"),
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


@app.post("/suggest", response_model=schemas.SuggestResponse)
async def suggest(
    req: schemas.SuggestRequest,
    x_ai_assistant_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> schemas.SuggestResponse:
    _check_secret(x_ai_assistant_secret)

    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="DeepSeek API key is not configured")

    try:
        agent = await crud.get_agent(db, req.agent_id)
        if not agent:
            agent = await crud.get_default_agent(db)
        if not agent:
            raise HTTPException(status_code=500, detail="No AI agent configured")

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": agent.system_prompt + _SUGGEST_PROMPT}
        ]

        if req.context:
            messages.append(_build_context_message(req.context))

        response = await httpx.AsyncClient().post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "max_tokens": 512,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"]
        parsed = _parse_suggestion(raw_reply)
        return schemas.SuggestResponse(**parsed)
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
    # For small content, store as a single document. For long content, store the
    # first chunk and accept that future improvements may store all chunks.
    content_to_store = chunks[0] if chunks else req.content
    embedding = await _embed_text(content_to_store)
    doc = await crud.create_document(
        db,
        source=req.source,
        title=req.title,
        content=content_to_store,
        content_type=req.content_type,
        embedding=embedding,
        metadata=req.metadata,
    )
    return schemas.DocumentOut.model_validate(doc)


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
    docs = await crud.list_documents(db, source=source, content_type=content_type, limit=limit, offset=offset)
    return [schemas.DocumentOut.model_validate(d) for d in docs]


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

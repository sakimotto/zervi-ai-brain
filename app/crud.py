import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import models


# ------------------------------------------------------------------
# Agents & Skills
# ------------------------------------------------------------------
async def get_agent(db: AsyncSession, agent_id: int) -> Optional[models.AIAgent]:
    result = await db.execute(
        select(models.AIAgent)
        .where(models.AIAgent.id == agent_id)
        .options(selectinload(models.AIAgent.skills))
    )
    return result.scalar_one_or_none()


async def get_default_agent(db: AsyncSession) -> Optional[models.AIAgent]:
    result = await db.execute(
        select(models.AIAgent)
        .where(models.AIAgent.is_active.is_(True))
        .order_by(models.AIAgent.id)
        .options(selectinload(models.AIAgent.skills))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_agents(db: AsyncSession, active_only: bool = True) -> Sequence[models.AIAgent]:
    query = select(models.AIAgent).options(selectinload(models.AIAgent.skills))
    if active_only:
        query = query.where(models.AIAgent.is_active.is_(True))
    query = query.order_by(models.AIAgent.id)
    result = await db.execute(query)
    return result.scalars().all()


async def ensure_default_agent_and_skills(db: AsyncSession, default_prompt: str) -> models.AIAgent:
    """Idempotently seed a default Saki agent and the standard tool skills."""
    result = await db.execute(select(models.AIAgent).where(models.AIAgent.id == 1))
    agent = result.scalar_one_or_none()

    default_skills = [
        {
            "name": "Low_Risk_Tools",
            "tool_schemas_json": [
                {
                    "tool": "create_activity",
                    "description": "Create a follow-up activity on a record.",
                    "params": {
                        "res_model": "string",
                        "res_id": "integer",
                        "summary": "string",
                        "note": "string (optional)",
                        "date_deadline": "YYYY-MM-DD (optional)",
                    },
                },
                {
                    "tool": "post_chatter_message",
                    "description": "Post a note or comment to a record's chatter.",
                    "params": {
                        "res_model": "string",
                        "res_id": "integer",
                        "message": "string",
                        "message_type": "comment|note",
                    },
                },
            ],
        },
        {
            "name": "Sales_Tools",
            "tool_schemas_json": [
                {
                    "tool": "confirm_sales_order",
                    "description": "Confirm a sales order quotation.",
                    "params": {
                        "res_model": "sale.order",
                        "res_id": "integer",
                        "confirmation_message": "string",
                    },
                }
            ],
        },
        {
            "name": "Inventory_Tools",
            "tool_schemas_json": [
                {
                    "tool": "validate_picking",
                    "description": "Validate a stock picking transfer.",
                    "params": {
                        "res_model": "stock.picking",
                        "res_id": "integer",
                        "confirmation_message": "string",
                    },
                }
            ],
        },
        {
            "name": "Manufacturing_Tools",
            "tool_schemas_json": [
                {
                    "tool": "done_manufacturing_order",
                    "description": "Mark a manufacturing order as done.",
                    "params": {
                        "res_model": "mrp.production",
                        "res_id": "integer",
                        "confirmation_message": "string",
                    },
                }
            ],
        },
        {
            "name": "Search_Tools",
            "tool_schemas_json": [
                {
                    "tool": "search_records",
                    "description": "Search Odoo records by model and domain and return a compact summary.",
                    "params": {
                        "res_model": "string",
                        "domain": "list of domain tuples, e.g. [['state','=','draft']]",
                        "limit": "integer (optional, default 20)",
                        "fields": "list of field names to read (optional)",
                    },
                }
            ],
        },
    ]

    skill_records: List[models.AISkill] = []
    for skill_data in default_skills:
        result = await db.execute(select(models.AISkill).where(models.AISkill.name == skill_data["name"]))
        skill = result.scalar_one_or_none()
        if not skill:
            skill = models.AISkill(
                name=skill_data["name"],
                tool_schemas_json=skill_data["tool_schemas_json"],
            )
            db.add(skill)
            await db.flush()
        skill_records.append(skill)

    if not agent:
        agent = models.AIAgent(
            id=1,
            name="Saki_Default",
            system_prompt=default_prompt,
            is_active=True,
        )
        db.add(agent)
        await db.flush()

    # Ensure the default agent is linked to all default skills.
    # Avoid lazy-loading agent.skills by querying the link table directly.
    link_result = await db.execute(
        select(models.AgentSkillLink.skill_id).where(models.AgentSkillLink.agent_id == agent.id)
    )
    linked_skill_ids = {row[0] for row in link_result.all()}
    for skill in skill_records:
        if skill.id not in linked_skill_ids:
            await db.execute(
                insert(models.AgentSkillLink).values(agent_id=agent.id, skill_id=skill.id)
            )

    await db.commit()

    # Return the agent with skills eagerly loaded.
    result = await db.execute(
        select(models.AIAgent)
        .where(models.AIAgent.id == agent.id)
        .options(selectinload(models.AIAgent.skills))
    )
    return result.scalar_one()


# ------------------------------------------------------------------
# Chat Sessions
# ------------------------------------------------------------------
async def create_session(
    db: AsyncSession, user_id: int, odoo_context_json: Optional[Dict[str, Any]] = None
) -> models.ChatSession:
    session = models.ChatSession(
        user_id=user_id,
        odoo_context_json=odoo_context_json or {},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: str) -> Optional[models.ChatSession]:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None
    result = await db.execute(select(models.ChatSession).where(models.ChatSession.id == sid))
    return result.scalar_one_or_none()


async def get_sessions_for_user(db: AsyncSession, user_id: int) -> Sequence[models.ChatSession]:
    result = await db.execute(
        select(models.ChatSession)
        .where(models.ChatSession.user_id == user_id)
        .order_by(models.ChatSession.updated_at.desc())
    )
    return result.scalars().all()


# ------------------------------------------------------------------
# Chat Messages
# ------------------------------------------------------------------
async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    tool_calls_json: Optional[Dict[str, Any]] = None,
    token_count: Optional[int] = None,
) -> models.ChatMessage:
    sid = uuid.UUID(session_id)
    message = models.ChatMessage(
        session_id=sid,
        role=role,
        content=content,
        tool_calls_json=tool_calls_json,
        token_count=token_count,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_recent_messages(
    db: AsyncSession, session_id: str, limit: int = 50
) -> Sequence[models.ChatMessage]:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return []
    result = await db.execute(
        select(models.ChatMessage)
        .where(models.ChatMessage.session_id == sid)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ------------------------------------------------------------------
# Embeddings / Semantic Search
# ------------------------------------------------------------------
async def save_embedding(
    db: AsyncSession, message_id: str, embedding: List[float]
) -> models.MessageEmbedding:
    mid = uuid.UUID(message_id)
    emb = models.MessageEmbedding(message_id=mid, embedding=embedding)
    db.add(emb)
    await db.commit()
    return emb


async def search_similar_messages(
    db: AsyncSession,
    user_id: int,
    embedding: List[float],
    limit: int = 5,
) -> Sequence[Tuple[models.ChatMessage, float]]:
    """Return (message, cosine_distance) pairs for the user's past messages."""
    result = await db.execute(
        select(models.ChatMessage, models.MessageEmbedding.embedding.cosine_distance(embedding).label("distance"))
        .join(models.MessageEmbedding)
        .join(models.ChatSession)
        .where(models.ChatSession.user_id == user_id)
        .order_by("distance")
        .limit(limit)
    )
    return result.all()


# ------------------------------------------------------------------
# Documents
# ------------------------------------------------------------------
async def create_document(
    db: AsyncSession,
    source: str,
    title: str,
    content: str,
    content_type: str,
    embedding: Optional[List[float]],
    metadata: Optional[Dict[str, Any]] = None,
) -> models.Document:
    doc = models.Document(
        source=source,
        title=title,
        content=content,
        content_type=content_type,
        embedding=embedding,
        metadata_json=metadata or {},
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def list_documents(
    db: AsyncSession,
    source: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[models.Document]:
    query = select(models.Document).order_by(models.Document.created_at.desc())
    if source:
        query = query.where(models.Document.source == source)
    if content_type:
        query = query.where(models.Document.content_type == content_type)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


async def get_document(db: AsyncSession, doc_id: str) -> Optional[models.Document]:
    try:
        did = uuid.UUID(doc_id)
    except ValueError:
        return None
    result = await db.execute(select(models.Document).where(models.Document.id == did))
    return result.scalar_one_or_none()


async def delete_document(db: AsyncSession, doc_id: str) -> bool:
    doc = await get_document(db, doc_id)
    if not doc:
        return False
    await db.delete(doc)
    await db.commit()
    return True


async def search_similar_documents(
    db: AsyncSession,
    embedding: List[float],
    limit: int = 5,
) -> Sequence[Tuple[models.Document, float]]:
    result = await db.execute(
        select(models.Document, models.Document.embedding.cosine_distance(embedding).label("distance"))
        .where(models.Document.embedding.isnot(None))
        .order_by("distance")
        .limit(limit)
    )
    return result.all()


# ------------------------------------------------------------------
# Facts
# ------------------------------------------------------------------
async def create_fact(
    db: AsyncSession,
    user_id: int,
    category: str,
    key: str,
    value: str,
    embedding: Optional[List[float]] = None,
) -> models.Fact:
    fact = models.Fact(
        user_id=user_id,
        category=category,
        key=key,
        value=value,
        embedding=embedding,
    )
    db.add(fact)
    await db.commit()
    await db.refresh(fact)
    return fact


async def list_facts(
    db: AsyncSession,
    user_id: int,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[models.Fact]:
    query = select(models.Fact).where(models.Fact.user_id == user_id).order_by(models.Fact.created_at.desc())
    if category:
        query = query.where(models.Fact.category == category)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


async def delete_fact(db: AsyncSession, fact_id: str) -> bool:
    try:
        fid = uuid.UUID(fact_id)
    except ValueError:
        return False
    result = await db.execute(select(models.Fact).where(models.Fact.id == fid))
    fact = result.scalar_one_or_none()
    if not fact:
        return False
    await db.delete(fact)
    await db.commit()
    return True


async def search_similar_facts(
    db: AsyncSession,
    user_id: int,
    embedding: List[float],
    limit: int = 5,
) -> Sequence[Tuple[models.Fact, float]]:
    result = await db.execute(
        select(models.Fact, models.Fact.embedding.cosine_distance(embedding).label("distance"))
        .where(models.Fact.user_id == user_id)
        .where(models.Fact.embedding.isnot(None))
        .order_by("distance")
        .limit(limit)
    )
    return result.all()

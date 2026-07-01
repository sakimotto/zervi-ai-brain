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

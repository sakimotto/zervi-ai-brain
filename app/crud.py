import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import models, seed_data


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


async def create_agent(
    db: AsyncSession,
    name: str,
    system_prompt: str,
    is_active: bool = True,
    skill_ids: Optional[List[int]] = None,
) -> models.AIAgent:
    agent = models.AIAgent(
        name=name,
        system_prompt=system_prompt,
        is_active=is_active,
    )
    db.add(agent)
    await db.flush()

    if skill_ids:
        # Validate that every supplied skill exists before linking.
        skill_ids = list(set(skill_ids))
        result = await db.execute(
            select(models.AISkill.id).where(models.AISkill.id.in_(skill_ids))
        )
        valid_ids = {row[0] for row in result.all()}
        invalid_ids = set(skill_ids) - valid_ids
        if invalid_ids:
            raise ValueError(f"Invalid skill IDs: {sorted(invalid_ids)}")
        for skill_id in valid_ids:
            await db.execute(
                insert(models.AgentSkillLink).values(agent_id=agent.id, skill_id=skill_id)
            )
        await db.flush()

    await db.commit()
    # Reload with skills.
    result = await db.execute(
        select(models.AIAgent)
        .where(models.AIAgent.id == agent.id)
        .options(selectinload(models.AIAgent.skills))
    )
    return result.scalar_one()


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
                },
                {
                    "tool": "get_inventory_valuation_setup",
                    "description": (
                        "Return the inventory valuation setup for all product categories, "
                        "including cost method, valuation method, and stock valuation/input/output accounts. "
                        "Use this to answer questions like 'What cost method do we use?' or 'How is inventory valued?'"
                    ),
                    "params": {},
                },
            ],
        },
        {
            "name": "Accounting_Tools",
            "tool_schemas_json": [
                {
                    "tool": "get_coa_summary",
                    "description": (
                        "Return a grouped summary of the chart of accounts for a given code prefix. "
                        "Use this to answer questions like 'How does our COA manage inventory write-downs?' "
                        "by calling it with prefix '113' for inventory asset accounts and '5' for expense accounts."
                    ),
                    "params": {
                        "prefix": "string (optional, e.g. '113' or '5')",
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
                    "description": (
                        "Search Odoo records by model and domain and return a compact summary. "
                        "Use this whenever the user asks for data that is not in the provided screen context. "
                        "Examples: search account.account with domain [['code','=like','113%']] to list inventory asset accounts; "
                        "search product.template with domain [['type','=','product']] to list storable products."
                    ),
                    "params": {
                        "res_model": "string (Odoo model technical name, e.g. 'account.account')",
                        "domain": "list of domain tuples, e.g. [['state','=','draft']]",
                        "limit": "integer (optional, default 50, max 100)",
                        "fields": "list of field names to read (optional, e.g. ['code','name','account_type'])",
                    },
                },
                {
                    "tool": "count_records",
                    "description": (
                        "Count Odoo records, optionally grouped by a field. "
                        "Use this whenever the user asks 'how many', 'count', 'number of', or wants a breakdown by category/status/etc. "
                        "Examples: count product.template grouped by categ_id to see how many products per category; "
                        "count sale.order with domain [['state','=','sale']] to see confirmed orders."
                    ),
                    "params": {
                        "res_model": "string (Odoo model technical name, e.g. 'product.template')",
                        "domain": "list of domain tuples (optional)",
                        "groupby": "string field name to group by (optional, e.g. 'categ_id')",
                        "limit": "integer (optional, max 100 groups)",
                    },
                },
            ],
        },
        {
            "name": "Engineering_Tools",
            "tool_schemas_json": [
                {
                    "tool": "search_engineering_documents",
                    "description": (
                        "Search engineering documents (patterns, CAD files, drawings, fitting instructions, CNC cut files) by code, type, product, BOM, or state. "
                        "Use this when the user asks about engineering documents, patterns, CAD, drawings, or CNC files."
                    ),
                    "params": {
                        "code": "string (optional, partial document code)",
                        "doc_type": "string (optional, one of: pattern, cad, drawing, fitting_instruction, cnc_file, spec, other)",
                        "product_id": "integer product.template id (optional)",
                        "bom_id": "integer mrp.bom id (optional)",
                        "state": "string (optional, one of: draft, review, approved, released, obsolete)",
                        "limit": "integer (optional, default 20, max 50)",
                    },
                },
                {
                    "tool": "list_open_engineering_tasks",
                    "description": (
                        "List open engineering tasks (pattern development, CAD development, sewing drawings, etc.) filtered by project or subtype. "
                        "Use this when the user asks about open engineering work or R&D tasks."
                    ),
                    "params": {
                        "project_id": "integer project.project id (optional)",
                        "task_subtype": "string (optional, one of: pattern_dev, cad_dev, sewing_drawing, fitting_instruction, cnc_file, revision, sample, test, other)",
                        "limit": "integer (optional, default 20, max 50)",
                    },
                },
                {
                    "tool": "create_engineering_project",
                    "description": (
                        "Create a new engineering/R&D project. Use this when the user asks to start a new R&D project, pattern project, CAD project, or engineering project."
                    ),
                    "params": {
                        "name": "string (project name, required)",
                        "zervi_eng_type": "string (one of: rnd, pattern, cad, sample, npi, other, default other)",
                        "zervi_product_line": "string (one of: seat_cover, tent, garment, fitness, other, default other)",
                        "zervi_target_product_id": "integer product.template id (optional)",
                    },
                },
                {
                    "tool": "add_engineering_task",
                    "description": (
                        "Add an engineering task to an existing project. Use this when the user asks to add a pattern task, CAD task, drawing task, fitting instruction task, CNC task, etc."
                    ),
                    "params": {
                        "project_id": "integer project.project id (required)",
                        "name": "string (task name, required)",
                        "zervi_task_subtype": "string (one of: pattern_dev, cad_dev, sewing_drawing, fitting_instruction, cnc_file, revision, sample, test, other)",
                        "zervi_deliverable_type": "string (one of: file, drawing, bom_update, sample, report, none, default none)",
                        "zervi_bom_id": "integer mrp.bom id (optional)",
                    },
                },
                {
                    "tool": "link_bom_to_project",
                    "description": (
                        "Link a manufacturing BOM to an engineering project. Use this when the user asks to attach, link, or associate a BOM with a project."
                    ),
                    "params": {
                        "project_id": "integer project.project id (required)",
                        "bom_id": "integer mrp.bom id (required)",
                    },
                },
                {
                    "tool": "create_engineering_document",
                    "description": (
                        "Create a new engineering document header (pattern, CAD, drawing, fitting instruction, CNC file, spec, or other). "
                        "Use this when the user asks to create/register a new engineering document."
                    ),
                    "params": {
                        "name": "string document title (required)",
                        "doc_type": "string (required, one of: pattern, cad, drawing, fitting_instruction, cnc_file, spec, other)",
                        "code": "string document code (optional, auto-generated if omitted)",
                        "project_id": "integer project.project id (optional)",
                        "task_id": "integer project.task id (optional)",
                        "product_id": "integer product.template id (optional)",
                        "bom_id": "integer mrp.bom id (optional)",
                    },
                },
                {
                    "tool": "create_engineering_document_revision",
                    "description": (
                        "Create a new revision for an existing engineering document, optionally uploading a file. "
                        "Use this when the user asks to add a revision, upload a file to a document, or release a new version."
                    ),
                    "params": {
                        "document_id": "integer zervi.engineering.document id (required)",
                        "name": "string revision name (required, e.g. 'A', 'Rev 1')",
                        "change_note": "string description of changes (optional)",
                        "attachment_id": "integer ir.attachment id (optional if attachment_data provided)",
                        "attachment_filename": "string filename (required if attachment_data provided)",
                        "attachment_data": "base64-encoded file content (optional)",
                        "state": "string (optional, one of: draft, review, approved, released, obsolete; default draft)",
                    },
                },
            ],
        },
        {
            "name": "Purchasing_Tools",
            "tool_schemas_json": [
                {
                    "tool": "confirm_purchase_order",
                    "description": "Confirm a purchase order quotation.",
                    "params": {
                        "res_model": "purchase.order",
                        "res_id": "integer",
                        "confirmation_message": "string",
                    },
                }
            ],
        },
        {
            "name": "Invoicing_Tools",
            "tool_schemas_json": [
                {
                    "tool": "create_invoice",
                    "description": "Create a customer invoice from a confirmed sales order.",
                    "params": {
                        "res_model": "sale.order",
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
        else:
            # Refresh default skill schemas on startup so new tools are added
            # to existing deployments. Custom skills (not in default_skills)
            # are left untouched.
            if skill.tool_schemas_json != skill_data["tool_schemas_json"]:
                skill.tool_schemas_json = skill_data["tool_schemas_json"]
                await db.flush()
        skill_records.append(skill)

    skill_by_name = {skill.name: skill for skill in skill_records}

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

    # Seed sample departmental agents using the richer prompts in seed_data.py.
    for name, prompt in seed_data.DEPARTMENT_PROMPTS.items():
        result = await db.execute(select(models.AIAgent).where(models.AIAgent.name == name))
        dept_agent = result.scalar_one_or_none()
        if not dept_agent:
            dept_agent = models.AIAgent(
                name=name,
                system_prompt=prompt,
                is_active=True,
            )
            db.add(dept_agent)
            await db.flush()
        elif dept_agent.system_prompt != prompt:
            # Keep prompts up to date when seed data changes.
            dept_agent.system_prompt = prompt
            await db.flush()

        link_result = await db.execute(
            select(models.AgentSkillLink.skill_id).where(models.AgentSkillLink.agent_id == dept_agent.id)
        )
        linked_skill_ids = {row[0] for row in link_result.all()}
        for skill_name in seed_data.DEPARTMENT_SKILLS.get(name, []):
            skill = skill_by_name.get(skill_name)
            if skill and skill.id not in linked_skill_ids:
                await db.execute(
                    insert(models.AgentSkillLink).values(agent_id=dept_agent.id, skill_id=skill.id)
                )

    await db.commit()

    # Return the default agent with skills eagerly loaded.
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


async def ensure_department_knowledge(
    db: AsyncSession,
    embed_fn: Any,
) -> None:
    """Seed sample RAG documents and facts, skipping duplicates."""
    return await seed_data.seed_department_knowledge(
        db,
        embed_fn=embed_fn,
        create_document=create_document,
        create_fact=create_fact,
        list_documents=list_documents,
        list_facts=list_facts,
    )


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


async def delete_documents_by_group(db: AsyncSession, group_id: str) -> int:
    from sqlalchemy import delete
    result = await db.execute(
        delete(models.Document).where(models.Document.metadata_json["group_id"].astext == group_id)
    )
    await db.commit()
    return result.rowcount


async def count_documents(db: AsyncSession) -> int:
    result = await db.execute(select(models.Document.id))
    return len(result.scalars().all())


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
    is_shared: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> models.Fact:
    fact = models.Fact(
        user_id=user_id,
        category=category,
        key=key,
        value=value,
        embedding=embedding,
        is_shared=is_shared,
        metadata_json=metadata or {},
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
    query = (
        select(models.Fact)
        .where((models.Fact.user_id == user_id) | (models.Fact.is_shared == True))
        .order_by(models.Fact.created_at.desc())
    )
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
        .where(
            ((models.Fact.user_id == user_id) | (models.Fact.is_shared == True))
            & (models.Fact.embedding.isnot(None))
        )
        .order_by("distance")
        .limit(limit)
    )
    return result.all()

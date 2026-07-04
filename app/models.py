import datetime
import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from .config import EMBEDDING_DIM
from .db import Base


class MessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, nullable=False, index=True)
    odoo_context_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    tool_calls_json = Column(JSONB, nullable=True)
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")
    embedding = relationship("MessageEmbedding", back_populates="message", uselist=False, cascade="all, delete-orphan")


class AIAgent(Base):
    __tablename__ = "ai_agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    system_prompt = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    skills = relationship("AISkill", secondary="agent_skill_link", back_populates="agents")


class AISkill(Base):
    __tablename__ = "ai_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    tool_schemas_json = Column(JSONB, nullable=False, default=list)

    agents = relationship("AIAgent", secondary="agent_skill_link", back_populates="skills")


class AgentSkillLink(Base):
    __tablename__ = "agent_skill_link"

    agent_id = Column(Integer, ForeignKey("ai_agents.id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("ai_skills.id", ondelete="CASCADE"), primary_key=True)


class MessageEmbedding(Base):
    __tablename__ = "message_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)

    message = relationship("ChatMessage", back_populates="embedding")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="")
    content = Column(Text, nullable=False)
    content_type = Column(String(50), nullable=False, default="text")
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class Fact(Base):
    __tablename__ = "facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, nullable=False, index=True)
    category = Column(String(100), nullable=False, default="general")
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    is_shared = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

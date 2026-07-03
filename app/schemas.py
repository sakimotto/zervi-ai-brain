import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str


class ChatRequest(BaseModel):
    message: str
    user_id: int
    session_id: Optional[str] = None
    agent_id: int = 1
    context: Dict[str, Any] = Field(default_factory=dict)
    history: Optional[List[ChatMessage]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: Optional[str] = None
    tool_request: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class SuggestRequest(BaseModel):
    user_id: int
    session_id: Optional[str] = None
    agent_id: int = 1
    context: Dict[str, Any] = Field(default_factory=dict)


class SuggestResponse(BaseModel):
    suggestion: str
    tool_request: Optional[Dict[str, Any]] = None


class SkillOut(BaseModel):
    id: int
    name: str
    tool_schemas_json: List[Dict[str, Any]]

    model_config = {"from_attributes": True}


class AgentOut(BaseModel):
    id: int
    name: str
    system_prompt: str
    is_active: bool
    skills: List[SkillOut]

    model_config = {"from_attributes": True}


class AgentCreate(BaseModel):
    name: str
    system_prompt: str
    is_active: bool = True
    skill_ids: Optional[List[int]] = Field(default_factory=list)


class SessionOut(BaseModel):
    id: uuid.UUID
    user_id: int
    odoo_context_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "json_encoders": {uuid.UUID: str}}


class DocumentCreate(BaseModel):
    source: str
    title: str
    content: str
    content_type: str = "text"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentOut(BaseModel):
    id: uuid.UUID
    source: str
    title: str
    content: str
    content_type: str
    metadata_json: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True, "json_encoders": {uuid.UUID: str}}


class FactCreate(BaseModel):
    category: str = "general"
    key: str
    value: str


class FactOut(BaseModel):
    id: uuid.UUID
    user_id: int
    category: str
    key: str
    value: str
    created_at: datetime

    model_config = {"from_attributes": True, "json_encoders": {uuid.UUID: str}}


class SearchResult(BaseModel):
    source: str
    title: str
    content: str
    metadata: Dict[str, Any]
    distance: Optional[float] = None

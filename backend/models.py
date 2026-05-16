"""Pydantic models for LAMA."""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------- Project ----------
class ProjectCreate(BaseModel):
    name: str
    source_tech: str
    target_tech: str
    description: Optional[str] = ""
    github_repo: Optional[str] = ""


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    name: str
    source_tech: str
    target_tech: str
    description: str = ""
    github_repo: str = ""
    stage: str = "Discovery"  # Discovery, DataModel, Architecture, CodeGen, Living
    stage_status: Dict[str, str] = Field(default_factory=lambda: {
        "Discovery": "active",
        "DataModel": "locked",
        "Architecture": "locked",
        "CodeGen": "locked",
        "Living": "locked",
    })
    freeze_gates: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# ---------- KB ----------
class KBFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    project_id: str
    filename: str
    filetype: str
    size: int
    chunk_count: int = 0
    entity_count: int = 0
    status: str = "uploaded"  # uploaded, processed
    created_at: str = Field(default_factory=_now_iso)


class KBChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    project_id: str
    file_id: str
    chunk_index: int
    content: str
    created_at: str = Field(default_factory=_now_iso)


class KBStatus(BaseModel):
    project_id: str
    files: int
    chunks: int
    entities: int
    classes: int
    methods: int
    tables: int
    columns: int
    roles: int
    relationships: int
    toon_size: int


# ---------- Chat ----------
class ChatRequest(BaseModel):
    project_id: str
    message: str
    model: str = "deepseek/deepseek-chat"
    stage: str = "Discovery"
    conversation_id: Optional[str] = None
    edit_mode: bool = False
    selected_section: Optional[str] = None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    conversation_id: str
    project_id: str
    role: str  # user / assistant / system
    content: str
    model: Optional[str] = None
    tokens: int = 0
    created_at: str = Field(default_factory=_now_iso)


# ---------- SRS ----------
class SRSSectionUpdate(BaseModel):
    section: str
    content: str


class SRSDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    project_id: str
    sections: Dict[str, str] = Field(default_factory=dict)
    frozen: bool = False
    frozen_at: Optional[str] = None
    frozen_by: Optional[str] = None
    version: int = 1
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# ---------- Prompts ----------
class PromptUpdate(BaseModel):
    template: str
    description: Optional[str] = None


class Prompt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str
    stage: str
    template: str
    description: str = ""
    version: int = 1
    updated_at: str = Field(default_factory=_now_iso)


class ProjectPrompt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_id: str
    key: str
    template: str
    description: str = ""
    version: int = 1
    updated_at: str = Field(default_factory=_now_iso)


# ---------- GitHub ----------
class GithubPushRequest(BaseModel):
    project_id: str
    repo_url: str
    token: str
    branch: str = "main"


# ---------- Pipeline / Stage handoff ----------
class StageContext(BaseModel):
    """Persisted snapshot of everything a stage produced.
    Loaded by the NEXT stage as its primary input context.
    This is the pipeline handoff mechanism between all 5 stages."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    project_id: str
    stage: str  # Discovery | DataModel | Architecture | CodeGen | Living
    frozen_at: str = ""
    frozen_by: str = "system"
    version: int = 1
    outputs: Dict[str, Any] = Field(default_factory=dict)
    toon_summary: str = ""
    sources: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

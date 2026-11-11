"""Immutable queue inputs and a validated subprocess/result protocol."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.pdf import PdfLimits


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class SkillSnapshot(FrozenModel):
    skill: str = Field(min_length=1, max_length=255)
    description: str | None = None
    mandatory: bool
    importance: int = Field(ge=1, le=5)
    required_evidence_level: int = Field(ge=1, le=5)
    assessment_method: Literal["resume", "interview"]
    aliases: list[str] = Field(default_factory=list)


class IntakeSnapshot(FrozenModel):
    schema_version: Literal["intake-queue-v1"] = "intake-queue-v1"
    gate_version: Literal["mandatory-presence-v1"] = "mandatory-presence-v1"
    title: str
    description: str
    company: str | None
    folder_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    folder_link: str
    skills: list[SkillSnapshot] = Field(min_length=1)
    pdf_limits: PdfLimits = Field(default_factory=PdfLimits)
    max_files: int = Field(ge=1, le=1000)
    file_timeout_seconds: float = Field(ge=1, le=600)
    embedding_model: str
    relevance_thresholds: list[float]


class SourceFile(FrozenModel):
    id: str = Field(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=1024)
    version: str = Field(min_length=1, max_length=255)
    size: str | None = None
    modifiedTime: str | None = None


class DocumentBlock(FrozenModel):
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    original_text: str
    normalized_text: str


class ResumeDocument(FrozenModel):
    page_count: int = Field(ge=1)
    blocks: list[DocumentBlock]


class Discovered(FrozenModel):
    status: Literal["discovered"] = "discovered"
    files: list[SourceFile]


class Ready(FrozenModel):
    status: Literal["ready_for_analysis"] = "ready_for_analysis"
    document: ResumeDocument


class Excluded(FrozenModel):
    status: Literal["excluded"] = "excluded"
    missing_skills: list[str]


class Failed(FrozenModel):
    status: Literal["failed"] = "failed"
    code: str = Field(max_length=64)
    message: str = Field(max_length=512)


WorkerResult = Annotated[Discovered | Ready | Excluded | Failed, Field(discriminator="status")]


class WorkerRequest(FrozenModel):
    action: Literal["discover", "screen"]
    snapshot: IntakeSnapshot
    file: SourceFile | None = None


class StartAssessmentRequest(BaseModel):
    idempotency_key: UUID


class AssessmentProgress(BaseModel):
    id: str
    job_id: int
    status: Literal["queued", "running", "screened", "failed"]
    phase: Literal["discovery", "screening", "screened", "failed"]
    total_files: int | None
    processed_files: int
    ready_for_analysis: int
    excluded: int
    failed: int
    current_file_name: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None

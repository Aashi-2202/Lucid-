"""Immutable queue inputs and a validated subprocess/result protocol."""

from datetime import datetime, date
import math
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.pdf import PdfLimits
from app.services.analysis import AnalysisResult
from app.schemas.competencies import CompetencyName, clean_competencies


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
    relevance_thresholds: list[float] = Field(min_length=4, max_length=4)
    analysis_version: Literal["resume-evidence-v1", "resume-evidence-v2"] | None = None
    summary_version: Literal["job-match-summary-v1"] | None = None
    additional_competencies: list[CompetencyName] = Field(default_factory=list, max_length=20)

    _clean_competencies = field_validator("additional_competencies")(clean_competencies)
    as_of_date: str = "1970-01-01"
    embedding_revision: Literal["1110a243fdf4706b3f48f1d95db1a4f5529b4d41"] = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    embedding_file: Literal["onnx/model_quint8_avx2.onnx"] = "onnx/model_quint8_avx2.onnx"

    @field_validator("relevance_thresholds")
    @classmethod
    def ordered_thresholds(cls, values):
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values) or any(a >= b for a,b in zip(values, values[1:])):
            raise ValueError("Relevance thresholds must be increasing finite values between zero and one")
        return values

    @field_validator("as_of_date")
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value


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
    analysis: AnalysisResult | None = None


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
    status: Literal["queued", "running", "screened", "completed", "failed"]
    phase: Literal["discovery", "screening", "assessing", "screened", "completed", "failed"]
    total_files: int | None
    processed_files: int
    ready_for_analysis: int
    assessed: int = 0
    excluded: int
    failed: int
    current_file_name: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None

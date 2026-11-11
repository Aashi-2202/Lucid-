"""The intake stage shared by future sequential assessment workers."""

from dataclasses import dataclass
from typing import Literal

from app.services.mandatory_gate import GateRequirement, check_mandatory_skills
from app.services.pdf import ExtractedResume, PdfLimits, extract_pdf
from app.services.processing_errors import ResumeProcessingError


@dataclass(frozen=True)
class ReadyForAnalysis:
    document: ExtractedResume
    status: Literal["ready_for_analysis"] = "ready_for_analysis"


@dataclass(frozen=True)
class ExcludedResume:
    # Retain only the gate outcome, not extracted candidate information.
    missing_skills: tuple[str, ...]
    status: Literal["excluded"] = "excluded"


@dataclass(frozen=True)
class ProcessingFailure:
    code: str
    message: str
    status: Literal["failed"] = "failed"


ScreeningResult = ReadyForAnalysis | ExcludedResume | ProcessingFailure


def screen_pdf(
    content: bytes,
    requirements: tuple[GateRequirement, ...],
    limits: PdfLimits | None = None,
) -> ScreeningResult:
    """Stop excluded/failed files before structured extraction or inference."""
    try:
        document = extract_pdf(content, limits)
    except ResumeProcessingError as exc:
        return ProcessingFailure(exc.code, exc.message)
    decision = check_mandatory_skills(document.text, requirements)
    if not decision.passed:
        return ExcludedResume(decision.missing_skills)
    return ReadyForAnalysis(document)

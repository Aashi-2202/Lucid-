"""Download and screen one file from a previously authorised job folder."""

from app.services.drive import download_pdf_file
from app.services.mandatory_gate import GateRequirement
from app.services.pdf import PdfLimits
from app.services.processing_errors import ResumeProcessingError
from app.services.screening import ProcessingFailure, ScreeningResult, screen_pdf


def screen_drive_file(
    file_id: str,
    *,
    folder_id: str,
    requirements: tuple[GateRequirement, ...],
    expected_version: str | None = None,
    limits: PdfLimits | None = None,
) -> ScreeningResult:
    """Return one isolated outcome; do not start inference or persist PDF bytes.

    Call from a worker thread/process, never directly on the async event loop.
    The caller must verify recruiter ownership before providing the folder ID.
    """
    limits = limits or PdfLimits()
    try:
        content = download_pdf_file(
            file_id, folder_id=folder_id, max_bytes=limits.max_bytes,
            expected_version=expected_version,
        )
    except ResumeProcessingError as exc:
        return ProcessingFailure(exc.code, exc.message)
    return screen_pdf(content, requirements, limits)

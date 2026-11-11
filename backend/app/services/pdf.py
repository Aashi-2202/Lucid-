"""Bounded text-PDF extraction with page and source-block provenance. No OCR."""

from dataclasses import dataclass
import math
import re
import time
import unicodedata

import pymupdf

from app.services.processing_errors import ResumeProcessingError


@dataclass(frozen=True)
class PdfLimits:
    max_bytes: int = 10 * 1024 * 1024
    max_pages: int = 20
    min_text_characters: int = 40
    max_text_characters: int = 200_000
    extraction_seconds: float = 20.0

    def __post_init__(self):
        for name in ("max_bytes", "max_pages", "min_text_characters", "max_text_characters"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.min_text_characters > self.max_text_characters:
            raise ValueError("Minimum text length exceeds the maximum")
        if not math.isfinite(self.extraction_seconds) or self.extraction_seconds <= 0:
            raise ValueError("extraction_seconds must be finite and positive")


@dataclass(frozen=True)
class TextBlock:
    page: int  # One-based, for display alongside the original PDF.
    bbox: tuple[float, float, float, float]
    original_text: str
    normalized_text: str


@dataclass(frozen=True)
class ExtractedResume:
    page_count: int
    blocks: tuple[TextBlock, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(block.normalized_text for block in self.blocks)


def normalize_text(text: str) -> str:
    """Normalize ligatures/spacing, retaining line breaks and skill punctuation."""
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or not unicodedata.category(c).startswith("C"))
    return "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()).strip()


def extract_pdf(content: bytes, limits: PdfLimits | None = None) -> ExtractedResume:
    """Extract usable text or raise a typed processing failure.

    The time budget is checked between native operations; it is not a hard
    process timeout. A future worker must isolate native parsing to enforce one.
    """
    limits = limits or PdfLimits()
    if len(content) > limits.max_bytes:
        raise ResumeProcessingError("file_too_large", "PDF exceeds the configured file-size limit.")
    if not content or b"%PDF-" not in content[:1024]:
        raise ResumeProcessingError("invalid_pdf", "The file is not a readable PDF.")

    started = time.monotonic()

    def check_time():
        if time.monotonic() - started > limits.extraction_seconds:
            raise ResumeProcessingError("extraction_timeout", "PDF text extraction exceeded its time budget.")

    blocks: list[TextBlock] = []
    text_length = 0
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            check_time()
            if not document.is_pdf:
                raise ResumeProcessingError("invalid_pdf", "The file is not a PDF.")
            if document.needs_pass:
                raise ResumeProcessingError("encrypted_pdf", "Password-protected PDFs are not supported.")
            if document.is_repaired:
                raise ResumeProcessingError("damaged_pdf", "The PDF required structural repair; provide a fresh PDF export.")
            if not document.page_count:
                raise ResumeProcessingError("unreadable_pdf", "The PDF has no pages.")
            if document.page_count > limits.max_pages:
                raise ResumeProcessingError("too_many_pages", "PDF exceeds the configured page limit.")

            for page in document:
                check_time()
                page_blocks: list[TextBlock] = []
                for raw in page.get_text("blocks", sort=True):
                    if raw[6] != 0:
                        continue
                    original = raw[4]
                    text_length += len(original)
                    if text_length > limits.max_text_characters:
                        raise ResumeProcessingError("too_much_text", "PDF exceeds the configured text limit.")
                    normalized = normalize_text(original)
                    if normalized:
                        if "\ufffd" in normalized:
                            raise ResumeProcessingError("unreadable_text", "PDF contains text that could not be decoded reliably.")
                        page_blocks.append(TextBlock(page.number + 1, tuple(raw[:4]), original, normalized))

                # A nearly textless page dominated by an image must not slip
                # through the gate as a page with no mandatory skill mentions.
                page_text = " ".join(b.normalized_text for b in page_blocks)
                if sum(c.isalnum() for c in page_text) < limits.min_text_characters:
                    page_area = page.rect.get_area()
                    image_area = 0.0
                    for image in page.get_image_info():
                        rect = pymupdf.Rect(image["bbox"]) & page.rect
                        image_area += rect.get_area()
                    if page_area and image_area / page_area >= 0.5:
                        raise ResumeProcessingError("ocr_required", "A PDF page requires OCR; use a selectable-text PDF.")
                blocks.extend(page_blocks)
                check_time()

            result = ExtractedResume(document.page_count, tuple(blocks))
            if sum(c.isalnum() for c in result.text) < limits.min_text_characters:
                raise ResumeProcessingError("insufficient_text", "Too little selectable text was extracted to screen this PDF.")
            return result
    except ResumeProcessingError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise ResumeProcessingError("unreadable_pdf", "The PDF could not be read safely.") from exc

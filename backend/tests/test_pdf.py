import unittest
from unittest.mock import patch

import pymupdf

from app.services.pdf import PdfLimits, extract_pdf, normalize_text
from app.services.processing_errors import ResumeProcessingError


RESUME_TEXT = "Skills: Python, SQL, C++, C#\nProjects: Built a reporting API with Python and SQL."


def make_pdf(*pages: str, encrypted: bool = False) -> bytes:
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        if encrypted:
            return document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
        return document.tobytes()


def make_scanned_pdf(*, with_text_page=False, tiled=False) -> bytes:
    with pymupdf.open() as document:
        if with_text_page:
            document.new_page().insert_text((72, 72), RESUME_TEXT)
        page = document.new_page()
        image = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 8, 8), False)
        image.clear_with(255)
        if tiled:
            for x, y in ((0, 0), (0.5, 0), (0, 0.5), (0.5, 0.5)):
                rect = pymupdf.Rect(x * page.rect.width, y * page.rect.height,
                                    (x + 0.5) * page.rect.width, (y + 0.5) * page.rect.height)
                page.insert_image(rect, pixmap=image)
        else:
            page.insert_image(page.rect, pixmap=image, keep_proportion=False)
        return document.tobytes()


class PdfExtractionTests(unittest.TestCase):
    def assert_failure(self, content, code, limits=None):
        with self.assertRaises(ResumeProcessingError) as raised:
            extract_pdf(content, limits)
        self.assertEqual(raised.exception.code, code)

    def test_preserves_pages_coordinates_original_text_and_skill_punctuation(self):
        result = extract_pdf(make_pdf(RESUME_TEXT, "Experience: Developed Python applications for a reporting team."))
        self.assertEqual(result.page_count, 2)
        self.assertEqual({block.page for block in result.blocks}, {1, 2})
        self.assertIn("C++", result.text)
        self.assertIn("C#", result.text)
        self.assertTrue(all(len(block.bbox) == 4 and block.bbox[2] > block.bbox[0] for block in result.blocks))
        self.assertIn("\n", result.blocks[0].original_text)

    def test_normalization_keeps_lines_and_symbols(self):
        self.assertEqual(normalize_text("  C++\t C#\r\n  .NET  \ufb01le\u200b\u00ad "), "C++ C#\n.NET file")

    def test_invalid_or_empty_file_is_failure(self):
        for data in (b"", b"not a pdf", b"%PDF-1.7\ngarbage"):
            with self.subTest(data=data):
                self.assert_failure(data, "invalid_pdf" if b"%PDF" not in data else "unreadable_pdf")

    def test_password_protected_file_is_failure(self):
        self.assert_failure(make_pdf(RESUME_TEXT, encrypted=True), "encrypted_pdf")

    def test_damaged_but_repairable_document_is_not_screened(self):
        content = make_pdf(RESUME_TEXT)
        # Remove the cross-reference table while leaving recoverable objects.
        damaged = content[:content.index(b"\nxref\n")]
        self.assert_failure(damaged, "damaged_pdf")

    def test_blank_or_tiny_text_is_failure(self):
        for text in ("", "123"):
            self.assert_failure(make_pdf(text), "insufficient_text")

    def test_scanned_and_mixed_documents_fail_before_screening(self):
        for mixed in (False, True):
            self.assert_failure(make_scanned_pdf(with_text_page=mixed), "ocr_required")

    def test_tiled_scan_is_not_mistaken_for_a_blank_page(self):
        self.assert_failure(make_scanned_pdf(with_text_page=True, tiled=True), "ocr_required")

    def test_blank_trailing_page_is_allowed(self):
        self.assertEqual(extract_pdf(make_pdf(RESUME_TEXT, "")).page_count, 2)

    def test_byte_limit(self):
        content = make_pdf(RESUME_TEXT)
        self.assert_failure(content, "file_too_large", PdfLimits(max_bytes=len(content) - 1))
        self.assertEqual(extract_pdf(content, PdfLimits(max_bytes=len(content))).page_count, 1)

    def test_page_limit(self):
        self.assert_failure(make_pdf(RESUME_TEXT, RESUME_TEXT), "too_many_pages", PdfLimits(max_pages=1))

    def test_text_limit(self):
        self.assert_failure(make_pdf(RESUME_TEXT), "too_much_text", PdfLimits(max_text_characters=40))

    def test_time_budget(self):
        with patch("app.services.pdf.time.monotonic", side_effect=[0, 21]):
            self.assert_failure(make_pdf(RESUME_TEXT), "extraction_timeout")

    def test_invalid_limits_rejected(self):
        for kwargs in ({"max_bytes": 0}, {"max_pages": -1}, {"max_pages": True},
                       {"extraction_seconds": float("nan")}, {"max_text_characters": 5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PdfLimits(**kwargs)

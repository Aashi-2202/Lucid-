import unittest
from unittest.mock import patch

from app.services.intake import screen_drive_file
from app.services.mandatory_gate import GateRequirement
from app.services.pdf import PdfLimits
from app.services.processing_errors import ResumeProcessingError
from test_pdf import make_pdf, RESUME_TEXT


class DriveIntakeTests(unittest.TestCase):
    @patch("app.services.intake.download_pdf_file")
    def test_download_feeds_extraction_and_gate(self, download):
        download.return_value = make_pdf(RESUME_TEXT)
        limits = PdfLimits(max_bytes=2048)
        result = screen_drive_file("resume_id", folder_id="job_folder", expected_version="7",
                                   requirements=(GateRequirement("Java", True),), limits=limits)
        self.assertEqual(result.status, "excluded")
        self.assertEqual(result.missing_skills, ("Java",))
        download.assert_called_once_with("resume_id", folder_id="job_folder", max_bytes=2048, expected_version="7")

    @patch("app.services.intake.screen_pdf")
    @patch("app.services.intake.download_pdf_file")
    def test_download_failure_never_runs_extraction_or_gate(self, download, screen):
        download.side_effect = ResumeProcessingError("file_access_denied", "Access denied.")
        result = screen_drive_file("resume_id", folder_id="job_folder", requirements=())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.code, "file_access_denied")
        screen.assert_not_called()

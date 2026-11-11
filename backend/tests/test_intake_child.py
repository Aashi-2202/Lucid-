import unittest
from unittest.mock import patch

from app.schemas.assessments import WorkerRequest, SourceFile
from app.services.intake_child import execute
from app.services.screening import screen_pdf
from queue_helpers import snapshot
from test_pdf import make_pdf, RESUME_TEXT


class IntakeChildTests(unittest.TestCase):
    @patch("app.services.intake_child.discover_pdf_files")
    def test_discovery_has_stable_name_and_id_order(self, discover):
        discover.return_value = [
            {"id": "b", "name": "same.pdf", "version": "3"},
            {"id": "a", "name": "Same.pdf", "version": "3"},
            {"id": "c", "name": "Z.pdf", "version": "3"},
        ]
        result = execute(WorkerRequest(action="discover", snapshot=snapshot()))
        self.assertEqual([file.id for file in result.files], ["a", "b", "c"])
        discover.assert_called_once_with("job_folder", max_files=100)

    @patch("app.services.intake_child.discover_pdf_files", return_value=[])
    def test_empty_folder_is_explicit_failure(self, _):
        result = execute(WorkerRequest(action="discover", snapshot=snapshot()))
        self.assertEqual(result.code, "no_pdfs")

    @patch("app.services.intake_child.screen_drive_file")
    def test_real_pdf_result_serializes_with_page_references(self, screen):
        screen.return_value = screen_pdf(make_pdf(RESUME_TEXT), ())
        result = execute(WorkerRequest(action="screen", snapshot=snapshot(),
                                      file=SourceFile(id="a", name="a.pdf", version="7")))
        self.assertEqual(result.status, "ready_for_analysis")
        self.assertEqual(result.document.blocks[0].page, 1)
        self.assertEqual(screen.call_args.kwargs["expected_version"], "7")
        self.assertEqual(screen.call_args.kwargs["requirements"][0].aliases, ("Python3",))

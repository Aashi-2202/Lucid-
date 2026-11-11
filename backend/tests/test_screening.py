import unittest
from unittest.mock import patch

from app.services.mandatory_gate import GateRequirement
from app.services.screening import screen_pdf, ReadyForAnalysis, ExcludedResume, ProcessingFailure
from test_pdf import make_pdf, make_scanned_pdf, RESUME_TEXT


class ScreeningTests(unittest.TestCase):
    def test_passing_resume_is_ready_but_has_no_score(self):
        result = screen_pdf(make_pdf(RESUME_TEXT), (GateRequirement("Python", True),))
        self.assertIsInstance(result, ReadyForAnalysis)
        self.assertIn("Python", result.document.text)
        self.assertFalse(hasattr(result, "score"))

    def test_exclusion_retains_only_missing_requirements(self):
        result = screen_pdf(make_pdf(RESUME_TEXT), (GateRequirement("Java", True),))
        self.assertIsInstance(result, ExcludedResume)
        self.assertEqual(result.missing_skills, ("Java",))
        self.assertFalse(hasattr(result, "document"))

    def test_bad_extraction_never_runs_gate(self):
        with patch("app.services.screening.check_mandatory_skills") as gate:
            for content in (b"not a pdf", make_scanned_pdf(with_text_page=True)):
                result = screen_pdf(content, (GateRequirement("Java", True),))
                self.assertIsInstance(result, ProcessingFailure)
            gate.assert_not_called()

    def test_one_failed_file_does_not_prevent_next_file(self):
        results = [screen_pdf(content, (GateRequirement("Python", True),))
                   for content in (b"broken", make_pdf(RESUME_TEXT))]
        self.assertEqual([r.status for r in results], ["failed", "ready_for_analysis"])

"""Labelled synthetic evidence examples, independent of model downloads."""
import unittest
from unittest.mock import patch

from app.schemas.assessments import IntakeSnapshot, ResumeDocument, SkillSnapshot, WorkerRequest, SourceFile
from app.services.analysis import analyse, duration_months, relevance_bucket
from app.services.intake_child import execute
from app.services.screening import ExcludedResume


def snapshot(skills=None):
    return IntakeSnapshot(title="Developer", description="Build backend data processing systems", company=None,
        folder_id="test_folder", folder_link="https://drive.google.com/drive/folders/test_folder",
        skills=skills or [skill()], max_files=10, file_timeout_seconds=60, embedding_model="all-MiniLM-L6-v2",
        relevance_thresholds=[.3,.5,.65,.8], analysis_version="resume-evidence-v1", as_of_date="2026-11-12")


def skill(**changes):
    return SkillSnapshot(**{"skill":"Python", "description":"Build Python services", "mandatory":False,
        "importance":5, "required_evidence_level":4, "assessment_method":"resume", "aliases":[], **changes})


def document(text):
    return ResumeDocument(page_count=1, blocks=[{"page":1,"bbox":[0,0,500,500],"original_text":text,"normalized_text":text}])


def exact_encoder(texts):
    return [[1.,0.] for text in texts]


class AnalysisTests(unittest.TestCase):
    def result(self, text, **changes):
        return analyse(document(text), snapshot([skill(**changes)]), encoder=exact_encoder)

    def test_named_skill_list_is_level_one_even_in_internship_section(self):
        result=self.result("Internships\nPython")
        self.assertEqual(result.skills[0].evidence_level,1)
        self.assertEqual(result.score,25)

    def test_coursework_and_applied_course_project_are_distinct(self):
        self.assertEqual(self.result("Coursework\nPython").skills[0].evidence_level,2)
        self.assertEqual(self.result("Education\nBuilt a Python forecasting project for coursework.").skills[0].evidence_level,3)

    def test_internship_role_context_does_not_turn_into_employment(self):
        result=self.result("Experience\nSoftware Engineer Intern\nJan 2023 - Dec 2023\nDeveloped Python APIs.")
        self.assertEqual(result.skills[0].evidence_level,4)
        self.assertIn("Intern",result.skills[0].evidence[0].context)

    def test_work_experience_needs_six_months_and_application(self):
        text="Experience\nSoftware engineer\nJan 2023 - Aug 2023\nBuilt Python reporting services."
        self.assertEqual(self.result(text).skills[0].evidence_level,5)
        self.assertEqual(self.result(text.replace("Aug","Mar")).skills[0].evidence_level,3)
        self.assertEqual(self.result(text.replace("Built Python reporting services.","Python")).skills[0].evidence_level,1)

    def test_future_dates_and_year_only_dates_cannot_establish_six_months(self):
        self.assertIsNone(duration_months("Jan 2026 - Dec 2027","2026-11-12"))
        self.assertIsNone(duration_months("2023 - 2024","2026-11-12"))
        self.assertEqual(duration_months("Jan 2026 - Present","2026-11-12"),10)

    def test_negation_and_future_learning_do_not_receive_skill_credit(self):
        for text in ("No experience with Python.","Planning to learn Python."):
            with self.subTest(text=text):
                result=self.result(text)
                self.assertEqual(result.skills[0].match_type,"absent")
                self.assertEqual(result.score,0)

    def test_explicit_basic_familiarity_is_not_elevated_by_unrelated_action(self):
        result=self.result("Projects\nBuilt Java services with basic Python familiarity.")
        self.assertEqual(result.skills[0].evidence_level,1)

    def test_highest_clearly_supported_evidence_is_selected(self):
        result=self.result("Skills\nPython\nProjects\nBuilt Python APIs.\nInternships\nDeveloped Python reporting services.")
        self.assertEqual(result.skills[0].evidence_level,4)

    def test_weighted_policy_matches_hand_calculation(self):
        result=analyse(document("Projects\nBuilt Python services and SQL reports."), snapshot([
            skill(importance=5,required_evidence_level=4), skill(skill="SQL",importance=3,required_evidence_level=3)]), encoder=exact_encoder)
        self.assertEqual(result.score,84.38)

    def test_absent_optional_retains_its_weight(self):
        def selective(texts):
            return [[1.,0.],[0.,1.],[1.,0.]]
        result=analyse(document("Projects\nBuilt Python services."),snapshot([skill(required_evidence_level=3),skill(skill="SQL",importance=5)]),encoder=selective)
        self.assertEqual(result.score,50)
        self.assertEqual(result.skills[1].match_type,"absent")

    def test_interview_only_does_not_run_encoder_or_produce_a_score(self):
        def must_not_run(_): raise AssertionError("Interview-only requirements must not be embedded")
        with patch("app.services.analysis.evidence_level",side_effect=AssertionError("Interview requirements must not infer an evidence level")):
            result=analyse(document("Skills\nPython"),snapshot([skill(assessment_method="interview",mandatory=True)]),encoder=must_not_run)
        self.assertIsNone(result.score)
        self.assertIsNone(result.skills[0].evidence_level)
        self.assertEqual(result.skills[0].skill_credit,0)

    def test_semantic_ambiguity_is_incomplete_and_keeps_zero_credit(self):
        def semantic(texts): return [[1.,0.],[.7,(1-.7**2)**.5]]
        result=analyse(document("Projects\nDeveloped server endpoints with FastAPI."),snapshot(),encoder=semantic)
        self.assertFalse(result.complete)
        self.assertEqual(result.skills[0].match_type,"semantic")
        self.assertIsNone(result.skills[0].evidence_level)
        self.assertEqual(result.score,0)

    def test_strong_semantic_application_can_support_project_evidence(self):
        def semantic(texts): return [[1.,0.],[.9,(1-.9**2)**.5]]
        result=analyse(document("Projects\nDeveloped server endpoints with FastAPI."),snapshot(),encoder=semantic)
        self.assertEqual(result.skills[0].evidence_level,3)
        self.assertEqual(result.skills[0].match_type,"semantic")
        self.assertTrue(result.complete)

    def test_relevance_is_bucketed_not_a_confidence_percentage(self):
        self.assertEqual([relevance_bucket(n,[.3,.5,.65,.8]) for n in (.2,.4,.6,.7,.9)], [0,.25,.5,.75,1])

    def test_excluded_resume_never_reaches_analysis_or_model(self):
        request=WorkerRequest(action="screen",snapshot=snapshot(),file=SourceFile(id="pdf",name="resume.pdf",version="1"))
        with patch("app.services.intake_child.screen_drive_file",return_value=ExcludedResume(missing_skills=("Python",))),patch("app.services.analysis.analyse",side_effect=AssertionError("must not run")):
            result=execute(request)
        self.assertEqual(result.status,"excluded")
        self.assertFalse(hasattr(result,"document"))

    def test_invalid_encoder_output_fails_instead_of_fabricating_a_score(self):
        with self.assertRaises(ValueError):
            analyse(document("Projects\nBuilt Python services."),snapshot(),encoder=lambda texts:[[float('nan'),0]]*len(texts))

    def test_model_failure_is_processing_failure_not_exclusion_or_zero_score(self):
        from app.services.pdf import ExtractedResume, TextBlock
        from app.services.screening import ReadyForAnalysis
        ready=ReadyForAnalysis(ExtractedResume(page_count=1,blocks=(TextBlock(1,(0,0,100,100),"Built Python services.","Built Python services."),)))
        request=WorkerRequest(action="screen",snapshot=snapshot(),file=SourceFile(id="pdf",name="resume.pdf",version="1"))
        with patch("app.services.intake_child.screen_drive_file",return_value=ready),patch("app.services.analysis.analyse",side_effect=RuntimeError("private diagnostic")):
            result=execute(request)
        self.assertEqual(result.status,"failed")
        self.assertEqual(result.code,"analysis_failed")
        self.assertNotIn("private diagnostic",result.message)
        self.assertFalse(hasattr(result,"document"))

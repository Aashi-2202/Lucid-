"""Requirement fulfilment, evidence grounding and legacy snapshot compatibility."""
import unittest
from unittest.mock import patch

from app.services.analysis import ANALYSIS_VERSION, analyse
from app.services.intake_child import execute
from app.schemas.assessments import WorkerRequest, SourceFile
from app.services.screening import ExcludedResume
from test_analysis import document, skill, snapshot, exact_encoder


def current_snapshot(skills=None):
    return snapshot(skills).model_copy(update={"analysis_version": ANALYSIS_VERSION})


def similarity_encoder(cosine):
    def encode(texts):
        return [[1., 0.], *[[cosine, (1-cosine**2)**.5] for _ in texts[1:]]]
    return encode


class FulfilmentTests(unittest.TestCase):
    def result(self, text, **changes):
        return analyse(document(text), current_snapshot([skill(**changes)]), encoder=exact_encoder)

    def test_explicit_application_meets_target_despite_low_semantic_similarity(self):
        snap = current_snapshot([skill(required_evidence_level=3)])
        for cosine in (-.2, .2, .49, .6, .9):
            with self.subTest(cosine=cosine):
                result=analyse(document("Projects\nDeveloped a Python-based application for tracking job applications."),snap,encoder=similarity_encoder(cosine))
                self.assertEqual(result.score,100)
                self.assertEqual(result.skills[0].evidence_credit,1)
                self.assertEqual(result.skills[0].skill_credit,1)
                self.assertEqual(result.version,ANALYSIS_VERSION)

    def test_weighted_partial_credit_and_cap_match_hand_calculation(self):
        # Python project 3/3, SQL mention 1/3, weights 5 and 3 -> 75.
        def encode(texts):
            return [[1.,0.],[0.,1.],[1.,0.],[0.,1.]]
        result=analyse(document("Projects\nBuilt Python reporting services.\nSkills\nSQL"),current_snapshot([
            skill(required_evidence_level=3,importance=5),skill(skill="SQL",required_evidence_level=3,importance=3)]),encoder=encode)
        self.assertEqual(result.score,75)
        self.assertEqual(self.result("Internships\nBuilt Python reporting services.",required_evidence_level=3).score,100)

    def test_level_two_of_three_and_level_one_of_three(self):
        self.assertEqual(self.result("Coursework\nPython",required_evidence_level=3).score,66.67)
        self.assertEqual(self.result("Skills\nPython",required_evidence_level=3).score,33.33)

    def test_absent_optional_keeps_weight_and_is_not_undetermined(self):
        def encode(texts): return [[1.,0.],[0.,1.],[1.,0.]]
        result=analyse(document("Projects\nBuilt Python reporting services."),current_snapshot([
            skill(required_evidence_level=3,importance=3),skill(skill="SQL",importance=3)]),encoder=encode)
        self.assertEqual(result.score,50)
        self.assertTrue(result.complete)
        self.assertEqual(result.skills[1].match_type,"absent")

    def test_high_similarity_does_not_invent_an_unmentioned_language(self):
        for cosine in (.7,.9,1.):
            result=analyse(document("Projects\nDeveloped server endpoints with FastAPI."),current_snapshot(),encoder=similarity_encoder(cosine))
            self.assertEqual(result.score,0)
            self.assertFalse(result.complete)
            self.assertEqual(result.skills[0].match_type,"semantic")
            self.assertIsNone(result.skills[0].evidence_level)

    def test_approved_alias_can_establish_application(self):
        result=self.result("Projects\nBuilt CPython reporting services.",aliases=["CPython"],required_evidence_level=3)
        self.assertEqual(result.score,100)

    def test_unrelated_actions_and_clauses_do_not_elevate_skill_mentions(self):
        for text in ("Projects\nPython; built Java services.", "Projects\nBuilt Java services and I know Python.",
                     "Projects\nPython. Developed Java APIs.", "Projects\nBuilt Java APIs and Python."):
            with self.subTest(text=text):
                result=self.result(text)
                self.assertEqual(result.skills[0].evidence_level,1)
                self.assertEqual(result.score,25)

    def test_general_project_summary_is_not_a_specific_application(self):
        result=self.result("Building hands-on projects using Python, data libraries, REST APIs, and FastAPI.")
        self.assertEqual(result.skills[0].evidence_level,1)

    def test_specific_ongoing_project_application_can_meet_level_three(self):
        result=self.result("Projects\nCurrently extending the project with Python and REST API functionality to make the application more scalable.",required_evidence_level=3)
        self.assertEqual(result.score,100)

    def test_negated_and_future_only_evidence_does_not_earn_credit(self):
        for text in ("No experience with Python.","Planning to learn Python.","Will build Python APIs."):
            with self.subTest(text=text):
                self.assertEqual(self.result(text).score,0)

    def test_basic_and_learning_claims_remain_mentions(self):
        for text in ("Projects\nBuilt Java services with basic Python familiarity.","Currently learning Python."):
            self.assertEqual(self.result(text).skills[0].evidence_level,1)

    def test_internship_and_duration_require_skill_linked_application(self):
        self.assertEqual(self.result("Internships\nBuilt Python reporting services.").skills[0].evidence_level,4)
        self.assertEqual(self.result("Experience\nSoftware engineer\nJan 2023 - Aug 2023\nBuilt Python reporting services.").skills[0].evidence_level,5)
        self.assertEqual(self.result("Experience\nSoftware engineer\nJan 2023 - Aug 2023\nPython; built Java services.").skills[0].evidence_level,1)

    def test_interview_requirements_stay_unscored_and_excluded_skip_analysis(self):
        with patch("app.services.analysis.linked_evidence_level",side_effect=AssertionError("must not infer levels")):
            result=self.result("Skills\nPython",assessment_method="interview")
        self.assertIsNone(result.score)
        self.assertEqual(result.skills[0].skill_credit,0)
        request=WorkerRequest(action="screen",snapshot=current_snapshot(),file=SourceFile(id="pdf",name="synthetic.pdf",version="1"))
        with patch("app.services.intake_child.screen_drive_file",return_value=ExcludedResume(missing_skills=("Python",))),patch("app.services.analysis.analyse",side_effect=AssertionError("must not run")):
            self.assertEqual(execute(request).status,"excluded")

    def test_legacy_snapshot_keeps_original_multiplier_and_label(self):
        old=snapshot([skill(required_evidence_level=3)])
        result=analyse(document("Projects\nBuilt Python reporting services."),old,encoder=similarity_encoder(.6))
        self.assertEqual(result.score,50)
        self.assertEqual(result.version,"resume-evidence-v1")
        # A saved, interrupted legacy run still resumes under its old policy.
        self.assertEqual(type(old).model_validate(old.model_dump()).analysis_version,"resume-evidence-v1")

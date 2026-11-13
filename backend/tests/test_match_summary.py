import unittest

from app.services.analysis import analyse
from app.services.match_summary import SUMMARY_VERSION
from test_analysis import document, skill, exact_encoder
from test_scoring_v2 import current_snapshot


def report(text, names=None, skills=None):
    snapshot = current_snapshot(skills).model_copy(update={
        "summary_version": SUMMARY_VERSION,
        "additional_competencies": names or ["Communication", "Learning Agility"],
    })
    return analyse(document(text), snapshot, encoder=exact_encoder)


class MatchSummaryTests(unittest.TestCase):
    def test_reporting_never_changes_score_completeness_or_skill_credits(self):
        text = "Projects\nBuilt Python reporting services.\nPresented findings to stakeholders.\nQuickly learned new tools."
        snapshot = current_snapshot()
        original = analyse(document(text), snapshot, encoder=exact_encoder)
        changed = report(text)
        self.assertEqual((changed.score, changed.complete, changed.skills), (original.score, original.complete, original.skills))
        self.assertEqual([item.status for item in changed.additional_competencies],["supporting_activity","supporting_activity"])

    def test_explicit_mentions_are_not_upgraded_to_verified_ability(self):
        result = report("Skills\nPython, Communication, Learning Agility")
        self.assertEqual([item.status for item in result.additional_competencies],["listed","listed"])
        self.assertIn("no specific supporting activity", result.job_match_summary)

    def test_missing_competencies_are_reported_without_penalty(self):
        result = report("Projects\nBuilt Python reporting services.")
        self.assertEqual(result.score,75)  # target 4, supported 3, unchanged
        self.assertTrue(result.complete)
        self.assertEqual([item.status for item in result.additional_competencies],["not_evidenced","not_evidenced"])
        self.assertIn("Not evidenced", result.job_match_summary)

    def test_supported_activity_is_a_brief_template_not_a_resume_quote(self):
        source = "Presented quarterly revenue forecasts and anomaly findings to client stakeholders in weekly reviews."
        result = report("Projects\nBuilt Python reporting services. " + source)
        finding = result.additional_competencies[0]
        self.assertEqual(finding.status,"supporting_activity")
        self.assertEqual(finding.pages,[1])
        self.assertNotIn(source, result.job_match_summary)
        self.assertNotIn("quarterly revenue", result.job_match_summary)
        self.assertIn("presenting or explaining", result.job_match_summary)

    def test_negated_and_future_activity_cannot_supply_support(self):
        for text in ("Never presented findings to stakeholders.", "Will present results to clients.", "No communication skills."):
            with self.subTest(text=text):
                result=report("Skills\nPython\n"+text)
                self.assertEqual(result.additional_competencies[0].status,"not_evidenced")

    def test_leadership_and_problem_activity_require_relevant_objects(self):
        names=["Leadership and Influence","Problem-Solving and Critical Thinking"]
        result=report("Experience\nLed a team of developers. Diagnosed production bottlenecks.",names)
        self.assertEqual([item.status for item in result.additional_competencies],["supporting_activity","supporting_activity"])
        unrelated=report("Projects\nLed a Python pipeline. Investigated a new dataset.",names)
        self.assertEqual([item.status for item in unrelated.additional_competencies],["not_evidenced","not_evidenced"])

    def test_custom_competency_uses_explicit_name_without_invented_synonyms(self):
        result=report("Skills\nTeamwork, Python",["Teamwork","Negotiation"])
        self.assertEqual([item.status for item in result.additional_competencies],["listed","not_evidenced"])

    def test_technical_summary_covers_matches_gaps_and_unknowns(self):
        result=report("Projects\nBuilt Python reporting services.",["Communication"],[
            skill(required_evidence_level=3),skill(skill="SQL",required_evidence_level=3)])
        self.assertIn("Python: application; meets requested evidence",result.job_match_summary)
        # Exact encoder deliberately retrieves every passage for SQL; unsupported
        # association remains an explicit review gap, never a claimed match.
        self.assertIn("SQL: possible evidence needs review",result.job_match_summary)
        absent=report("Skills\nPython",["Communication"],[skill(skill="SQL")])
        self.assertIn("SQL: not evidenced",absent.job_match_summary)

    def test_frozen_legacy_snapshot_does_not_gain_a_fabricated_report(self):
        result=analyse(document("Skills\nPython, Communication"),current_snapshot(),encoder=exact_encoder)
        self.assertIsNone(result.summary_version)
        self.assertIsNone(result.job_match_summary)
        self.assertEqual(result.additional_competencies,[])

import unittest

from app.services.mandatory_gate import GateRequirement, check_mandatory_skills


def missing(text, *skills):
    requirements = tuple(GateRequirement(skill, mandatory=True) for skill in skills)
    return check_mandatory_skills(text, requirements).missing_skills


class MandatoryGateTests(unittest.TestCase):
    def test_explicit_skills_and_case(self):
        self.assertEqual(missing("Skills: python, SQL", "Python", "SQL"), ())

    def test_approved_aliases_only(self):
        requirement = GateRequirement("PostgreSQL", True, ("Postgres",))
        self.assertTrue(check_mandatory_skills("Skills: Postgres", (requirement,)).passed)
        self.assertEqual(missing("Skills: Postgres", "PostgreSQL"), ("PostgreSQL",))

    def test_similar_skill_is_not_an_explicit_match(self):
        self.assertEqual(missing("Skills: Django and NoSQL", "Python", "SQL"), ("Python", "SQL"))

    def test_punctuation_and_substring_boundaries(self):
        self.assertEqual(missing("Skills: C++, C#, .NET, Node.js", "C++", "C#", ".NET", "Node.js"), ())
        self.assertEqual(missing("Skills: C++ and C#", "C"), ("C",))
        self.assertEqual(missing("Skills: ASP.NET", ".NET"), (".NET",))
        self.assertEqual(missing("Skills: Pythonic, SQLAlchemy, C++17", "Python", "SQL", "C++"), ("Python", "SQL", "C++"))

    def test_negation_and_future_plans_are_not_claims(self):
        examples = (
            "No experience with Python", "Not familiar with Python", "Without Python knowledge",
            "I lack Python experience", "I have never used Python", "I haven't used Python",
            "I don’t know Python", "Planning to learn Python", "I want to learn Python",
            "Python: none", "Python (no experience)", "Python - not used",
            "No experience with Node.js and Python", "No experience with\nPython",
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(missing(text, "Python"), ("Python",))

    def test_affirmative_occurrence_can_follow_negative_one(self):
        self.assertEqual(missing("Previously no Python. Projects: Built services using Python.", "Python"), ())

    def test_negation_does_not_leak_into_next_claim(self):
        for text in ("No Python, but SQL", "No Python. SQL", "No Python\nSQL", "Not only SQL but also Python"):
            with self.subTest(text=text):
                self.assertEqual(missing(text, "SQL"), ())

    def test_not_only_is_affirmative(self):
        self.assertEqual(missing("Not only Python but also SQL", "Python", "SQL"), ())

    def test_interview_skill_uses_same_presence_rule(self):
        self.assertEqual(missing("Skills: SQL", "Communication"), ("Communication",))
        self.assertEqual(missing("Skills: Communication", "Communication"), ())

    def test_nonmandatory_requirements_do_not_exclude(self):
        result = check_mandatory_skills("Skills: SQL", (GateRequirement("Python"),))
        self.assertTrue(result.passed)

    def test_all_missing_requirements_are_returned(self):
        self.assertEqual(missing("Skills: SQL", "Python", "Java", "SQL"), ("Python", "Java"))

    def test_blank_names_or_aliases_are_configuration_errors(self):
        for skill, aliases in ((" ", ()), ("SQL", (" ",)), ("\u200b", ()), ("SQL", ("\u200b",))):
            with self.assertRaises(ValueError):
                GateRequirement(skill, aliases=aliases)

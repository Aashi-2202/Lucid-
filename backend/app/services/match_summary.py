"""Versioned, deterministic reporting. Never contributes to scores or eligibility."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.services.mandatory_gate import GateRequirement, check_mandatory_skills

SUMMARY_VERSION = "job-match-summary-v1"


class CompetencyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    status: Literal["supporting_activity", "listed", "not_evidenced"]
    reason: str
    pages: list[int]


# Deliberately bounded activity signals. These describe claims in a resume,
# not measured communication, personality, leadership or learning ability.
_POLICIES = [
    ({"communication", "communication skills", "communications skills"},
     ("communication", "communication skills", "communications skills"),
     r"\b(?:presented|presenting|explained|communicated)\b.{0,100}\b(?:stakeholders?|clients?|customers?|audiences?|teams?|findings|results)\b",
     "Describes presenting or explaining work to others."),
    ({"leadership", "leadership and influence", "leadership & influence"},
     ("leadership", "leadership and influence", "mentoring"),
     r"\b(?:led|leading|mentored|mentoring|coached|coaching|coordinated)\b.{0,80}\b(?:teams?|developers?|engineers?|colleagues?|peers|members|people|students)\b",
     "Describes leading, mentoring or coordinating others."),
    ({"problem-solving", "problem solving", "critical thinking", "problem-solving and critical thinking", "problem solving and critical thinking"},
     ("problem-solving", "problem solving", "critical thinking"),
     r"\b(?:resolved|resolving|diagnosed|diagnosing|debugged|debugging|investigated)\b.{0,100}\b(?:issues?|bugs?|bottlenecks?|failures?|problems?|errors?)\b",
     "Describes investigating or resolving a specific problem."),
    ({"learning agility", "adaptability"},
     ("learning agility", "adaptability", "continuous learning"),
     r"\b(?:(?:quickly|rapidly)\s+(?:learned|learnt|adopted)|(?:learned|learnt|adopted)\s+(?:a\s+)?new)\b.{1,80}\b(?:tools?|technolog\w*|frameworks?|languages?|systems?|Python|SQL|Java|React|FastAPI)\b",
     "Describes learning or adopting a new tool or technology."),
]
_UNSUPPORTED = re.compile(r"\b(?:no|not|never|without|lack|lacks|lacking|plan(?:ning)? to|want to|hope to|will|would)\b", re.I)
_LEVELS = {1: "mention/basic familiarity", 2: "coursework", 3: "application", 4: "internship application", 5: "work application with stated duration"}


def competency_findings(entries, names):
    findings = []
    for name in names:
        policy = next((item for item in _POLICIES if name.casefold() in item[0]), None)
        terms = policy[1] if policy else (name,)
        listed, supporting = [], []
        for passage in entries:
            if _UNSUPPORTED.search(passage.text):
                continue
            if check_mandatory_skills(passage.text, (GateRequirement(terms[0], True, tuple(terms[1:])),)).passed:
                listed.append(passage)
            # Only activity passages, never names, contact blocks or job titles.
            if policy and re.search(policy[2], passage.text, re.I):
                supporting.append(passage)
        matches = supporting or listed
        findings.append(CompetencyFinding(
            name=name,
            status="supporting_activity" if supporting else "listed" if listed else "not_evidenced",
            reason=policy[3] if supporting else "Listed in the resume; no specific supporting activity found." if listed else "Not evidenced in the resume.",
            pages=sorted({passage.page for passage in matches})[:3],
        ))
    return findings


def job_match_summary(skills, findings):
    technical = []
    for skill in skills:
        if skill.assessment_method != "resume":
            detail = "interview requirement, unscored"
        elif skill.match_type == "absent":
            detail = "not evidenced"
        elif skill.evidence_level is None:
            detail = "possible evidence needs review"
        else:
            level = _LEVELS[skill.evidence_level]
            detail = f"{level}; meets requested evidence" if skill.evidence_credit >= 1 else f"{level}; below requested evidence"
        technical.append(f"{' '.join(skill.skill.split())}: {detail}")
    parts = ["Technical requirements — " + "; ".join(technical) + "."]
    if findings:
        parts.append("Additional competencies (unscored) — " + "; ".join(f"{item.name}: {item.reason.rstrip('.')}" for item in findings) + ".")
    return " ".join(parts)

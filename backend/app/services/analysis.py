"""Versioned, source-linked resume evidence policy and deterministic scoring."""
from datetime import date
import math
import re

from pydantic import BaseModel, ConfigDict, Field

from app.services.mandatory_gate import GateRequirement, check_mandatory_skills
from app.services.processing_errors import ResumeProcessingError

ANALYSIS_VERSION = "resume-evidence-v2"
LEGACY_ANALYSIS_VERSION = "resume-evidence-v1"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int
    block: int
    section: str
    text: str
    context: str = ""


class SkillAssessment(BaseModel):
    skill: str
    assessment_method: str
    mandatory: bool
    importance: int
    required_evidence_level: int | None
    evidence_level: int | None
    relevance: float
    evidence_credit: float
    skill_credit: float
    match_type: str
    reason: str
    evidence: list[Evidence]


class AnalysisResult(BaseModel):
    version: str = ANALYSIS_VERSION
    model: str
    model_revision: str
    model_file: str
    score: float | None
    complete: bool
    skills: list[SkillAssessment]
    sections: dict[str, list[Evidence]]
    extracted_skills: list[str]


_HEADINGS = {
    "skills": r"(?:technical |professional |core )?skills|technologies|technical expertise|competencies|technical proficiencies",
    "projects": r"(?:academic |personal |selected |technical )?projects|project experience",
    "education": r"education|academic qualifications|academic background|qualifications",
    "coursework": r"(?:relevant )?coursework|courses|certifications|training",
    "internships": r"internships?|internship experience",
    "experience": r"(?:(?:professional|work|relevant|employment) )?experience|employment(?: history)?|work history",
}
_ACTION = re.compile(r"\b(?:built|developed|implemented|designed|created|used|using|applied|deployed|automated|analysed|analyzed|optimised|optimized|delivered|maintained|integrated|trained|managed|led|engineered|tested|improved|collaborated|presented|conducted|wrote)\b", re.I)
_INTERN = re.compile(r"\bintern(?:ship)?\b", re.I)
_PROJECT = re.compile(r"\bproject\b", re.I)
_NEGATIVE = re.compile(r"\b(?:no|not|without|never|lack|lacks|plan to|planning to|want to|hope to)\b", re.I)
_MONTHS = {name.lower(): index for index, name in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
_DATE = re.compile(r"\b(?:(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)[ .,/-]+(20\d{2}|19\d{2})|(20\d{2})[-/](0?[1-9]|1[0-2])|(present|current|now))\b", re.I)


def duration_months(context, as_of):
    matches = list(_DATE.finditer(context))
    if len(matches) != 2 or not re.search(r"[-–—]|\bto\b", context[matches[0].end():matches[1].start()], re.I):
        return None
    def value(match):
        if match[5]:
            current = date.fromisoformat(as_of)
            return current.year * 12 + current.month
        if match[1]:
            return int(match[2]) * 12 + _MONTHS[match[1][:3].lower()]
        return int(match[3]) * 12 + int(match[4])
    end = value(matches[1])
    current = date.fromisoformat(as_of)
    months = end - value(matches[0])
    return months if 0 <= months <= 600 and end <= current.year * 12 + current.month else None


def passages(document):
    """Detect sections and bounded entries without inferring employer/degree facts."""
    result = []
    section, context = "other", ""
    for block_index, block in enumerate(document.blocks):
        pending = []
        def flush():
            if not pending:
                return
            text = " ".join(pending).strip()
            pending.clear()
            # Short overlapping-free passages stay under the encoder token budget.
            pieces = re.split(r"(?<=[.!?;])\s+(?=[A-Z•])", text)
            for piece in pieces:
                words = piece.split()
                for start in range(0, len(words), 80):
                    chunk = " ".join(words[start:start + 80])
                    if chunk:
                        result.append(Evidence(page=block.page, block=block_index, section=section,
                                               context=context[:300], text=chunk[:1000]))
        for raw in block.original_text.splitlines():
            line = raw.strip(" \t•●▪")
            if not line:
                flush()
                continue
            heading = line.strip(" :|-–—").casefold()
            found = next((key for key, pattern in _HEADINGS.items() if re.fullmatch(pattern, heading)), None)
            if found:
                flush()
                section, context = found, ""
                continue
            if len(list(_DATE.finditer(line))) >= 2 and len(line) < 220 and not _ACTION.search(line):
                flush()
                context = (context + " " + line).strip() if context and not _DATE.search(context) else line
                continue
            if section in ("experience", "internships") and len(line) < 140 and re.search(r"\b(?:intern|engineer|developer|analyst|consultant|manager|scientist)\b", line, re.I) and not _ACTION.search(line):
                flush()
                context = line
                continue
            if pending and raw.lstrip().startswith(("•", "●", "▪", "- ")):
                flush()
            pending.append(line)
        flush()
    if len(result) > 600:
        raise ResumeProcessingError("analysis_limit", "This document has too many passages for the current assessment limit.")
    return result


def evidence_level(passage, as_of):
    if passage.section == "coursework" or re.search(r"\b(?:coursework|course|certification|training program)\b", passage.text, re.I):
        if not (_ACTION.search(passage.text) and _PROJECT.search(passage.text)):
            return 2, "Skill explicitly linked to coursework or a learning programme."
    if not _ACTION.search(passage.text):
        return 1, "Explicit mention without an application description."
    if _INTERN.search(passage.context) or passage.section == "internships" or _INTERN.search(passage.text):
        return 4, "Skill application linked to an identified internship."
    if passage.section == "experience":
        months = duration_months(passage.context + " " + passage.text, as_of)
        if months is not None and months >= 6:
            return 5, "Skill application linked to a work entry spanning at least six months."
        return 3, "Work application described; six months of skill-linked duration is not established."
    if passage.section == "projects" or _PROJECT.search(passage.text):
        return 3, "Skill application described in a project."
    if passage.section in ("education", "coursework"):
        return 2, "Skill application linked to coursework or training."
    return 3, "Concrete skill application described; stronger experience context is not established."


def relevance_bucket(similarity, thresholds):
    if len(thresholds) != 4 or any(not math.isfinite(t) for t in thresholds) or sorted(thresholds) != thresholds:
        raise ValueError("Invalid relevance thresholds")
    return sum(similarity >= threshold for threshold in thresholds) / 4


_ACTION_V2 = re.compile(_ACTION.pattern.removesuffix(r")\b") + r"|building|developing|implementing|designing|creating|extending|extended|deploying|automating|integrating)\b", re.I)
_ARTIFACT = re.compile(r"\b(?:applications?|apps?|APIs?|endpoints?|services?|pipelines?|reports?|dashboards?|scripts?|models?|databases?|systems?|tools?|platforms?|websites?|backends?|frontends?|algorithms?|workflows?|tests?|queries|query|components?|classifiers?|forecasts?|processes|process|software|datasets?)\b", re.I)
_GENERAL_APPLICATION = re.compile(r"\b(?:hands[- ]on projects|(?:various|multiple|several) projects|strong foundation|proficient|familiarity)\b", re.I)
_PLANNED_APPLICATION = re.compile(r"\b(?:(?:will|would like to|plan(?:ning)? to|hope to|intend to|want to)\s+(?:build|develop|implement|extend|use|learn|study))\b", re.I)
_CLAUSES_V2 = re.compile(r"[;\n]|(?<=[.!?])\s+|\b(?:but|however|whereas|although)\b|,?\s+and\s+(?=(?:I|we)\s+|(?:know|learned|studied|built|developed|implemented|created|deployed|managed|led)\b)", re.I)


def evidence_passages_v2(document):
    """Keep a skill claim and its application in the same bounded clause."""
    result = []
    for passage in passages(document):
        for text in _CLAUSES_V2.split(passage.text):
            text = text.strip(" ,")
            if text:
                result.append(passage.model_copy(update={"text": text}))
    if len(result) > 600:
        raise ResumeProcessingError("analysis_limit", "This document has too many passages for the current assessment limit.")
    return result


def linked_evidence_level(passage, skill, as_of):
    """Conservative application checks; a retrieved association alone is not proof."""
    terms = sorted((skill.skill, *skill.aliases), key=len, reverse=True)
    pattern = re.compile(r"(?<![\w+#.])(?:" + "|".join(re.escape(term) for term in terms) + r")(?![\w+#])", re.I)
    occurrences = list(pattern.finditer(passage.text))
    for occurrence in occurrences:
        before = passage.text[max(0, occurrence.start() - 50):occurrence.start()]
        after = passage.text[occurrence.end():occurrence.end() + 45]
        if re.search(r"\b(?:basic|beginner|familiar with|knowledge of|learning)\s*$", before, re.I) or re.match(r"\s*\(?(?:basic|beginner)\b", after, re.I):
            return 1, "The resume describes a mention, learning or basic familiarity."
    if _GENERAL_APPLICATION.search(passage.text):
        return 1, "General application claim without a specific skill-linked task."
    actions = list(_ACTION_V2.finditer(passage.text))
    linked = False
    for occurrence in occurrences:
        for action in actions:
            if action.end() <= occurrence.start():
                between = passage.text[action.end():occurrence.start()]
                after = passage.text[occurrence.end():occurrence.end() + 100]
                # Either the skill qualifies a concrete artifact, or the action
                # names an artifact and links its implementation using the skill.
                linked = len(between.split()) <= 15 and (
                    bool(_ARTIFACT.search(after)) or
                    bool(_ARTIFACT.search(between) and re.search(r"\b(?:using|with|in|via)\b", between, re.I)))
            elif occurrence.end() <= action.start():
                between = passage.text[occurrence.end():action.start()]
                linked = bool(re.fullmatch(r"\s*[:—–-]\s*", between) and _ARTIFACT.search(passage.text[action.end():]))
            if linked:
                break
        if linked:
            break
    if not linked:
        if passage.section == "coursework" or re.search(r"\b(?:coursework|course|certification|training program)\b", passage.text, re.I):
            return 2, "Skill explicitly linked to coursework or a learning programme."
        return 1, "Explicit mention without a clearly linked concrete application."
    if _INTERN.search(passage.context) or passage.section == "internships" or _INTERN.search(passage.text):
        return 4, "Skill application linked to an identified internship."
    if passage.section == "experience":
        months = duration_months(passage.context + " " + passage.text, as_of)
        if months is not None and months >= 6:
            return 5, "Skill application linked to a work entry spanning at least six months."
        return 3, "Work application described; six months of skill-linked duration is not established."
    if passage.section in ("education", "coursework") and not _PROJECT.search(passage.text):
        return 2, "Skill application linked to coursework or training."
    return 3, "Concrete skill-linked application described in the resume."


def analyse(document, snapshot, encoder=None):
    from app.services.embeddings import MODEL_REPO, MODEL_REVISION, MODEL_FILE
    if snapshot.analysis_version not in (ANALYSIS_VERSION, LEGACY_ANALYSIS_VERSION) or snapshot.embedding_model not in (MODEL_REPO, "all-MiniLM-L6-v2"):
        raise ValueError("Unsupported analysis policy")
    current_policy = snapshot.analysis_version == ANALYSIS_VERSION
    entries = evidence_passages_v2(document) if current_policy else passages(document)
    requirements = snapshot.skills
    # Do not encode contact/header-only information. Explicit skill mentions remain
    # eligible even when the parser cannot identify their section.
    relevant = [p for p in entries if p.section != "other" or (_ACTION_V2 if current_policy else _ACTION).search(p.text) or any(
        check_mandatory_skills(p.text, (GateRequirement(s.skill, True, tuple(s.aliases)),)).passed for s in requirements)]
    queries = [f"{s.skill}. {s.description or ''}".strip() if current_policy else
               f"{s.skill}. {s.description or snapshot.title + '. ' + snapshot.description[:400]}" for s in requirements]
    if relevant and any(s.assessment_method == "resume" for s in requirements):
        if encoder is None:
            from app.services.embeddings import encode
            encoder = encode
        vectors = encoder(queries + [p.text for p in relevant])
        import numpy as np
        vectors = np.asarray(vectors)
        if vectors.ndim != 2 or len(vectors) != len(queries) + len(relevant) or not np.isfinite(vectors).all() or (np.linalg.norm(vectors, axis=1) < 1e-9).any():
            raise ValueError("The encoder returned invalid embeddings")
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        similarities = np.clip(vectors[:len(queries)] @ vectors[len(queries):].T, -1, 1)
    else:
        similarities = [[0.0] * len(relevant) for _ in requirements]
    results = []
    complete = True
    for index, skill in enumerate(requirements):
        interview = skill.assessment_method == "interview"
        matches = []
        for pos, passage in enumerate(relevant):
            if current_policy and _PLANNED_APPLICATION.search(passage.text):
                continue
            explicit = check_mandatory_skills(passage.text, (GateRequirement(skill.skill, True, tuple(skill.aliases)),)).passed
            cosine = float(similarities[index][pos])
            semantic = not explicit and cosine >= snapshot.relevance_thresholds[2] and bool((_ACTION_V2 if current_policy else _ACTION).search(passage.text)) and not _NEGATIVE.search(passage.text)
            if not explicit and not semantic:
                continue
            level, reason = (None, "Interview supporting signal.") if interview else linked_evidence_level(passage, skill, snapshot.as_of_date) if current_policy else evidence_level(passage, snapshot.as_of_date)
            # A moderate semantic association alone does not establish the skill
            # to application link. Keep it reviewable with zero provisional credit.
            if not interview and semantic and (current_policy or cosine < snapshot.relevance_thresholds[3]):
                level, reason = None, "Possible semantic evidence; the skill-to-application link needs review."
            if not current_policy and not interview and explicit:
                terms = [skill.skill, *skill.aliases]
                if any(re.search(r"\b(?:basic|beginner|familiar with|learning)\s+" + re.escape(term) + r"\b|" + re.escape(term) + r"\s*\(?(?:basic|beginner)\b", passage.text, re.I) for term in terms):
                    level, reason = 1, "The passage describes basic familiarity, not stronger application evidence."
            relevance = 0 if interview else max(0.25 if explicit else 0.0, relevance_bucket(cosine, snapshot.relevance_thresholds))
            credit = (1 if current_policy else relevance) * min(level / skill.required_evidence_level, 1) if level is not None else 0
            matches.append((level, credit, relevance, reason, passage, "explicit" if explicit else "semantic", cosine))
        matches.sort(key=lambda item: (item[0] or 0, item[1], item[6]) if current_policy else (item[0] or 0, item[1]), reverse=True)
        best = matches[0] if matches else None
        if not interview and best and best[0] is None:
            complete = False
        results.append(SkillAssessment(
            skill=skill.skill, assessment_method=skill.assessment_method, mandatory=skill.mandatory,
            importance=skill.importance, required_evidence_level=None if interview else skill.required_evidence_level,
            evidence_level=None if interview or best is None else best[0],
            relevance=0 if interview or best is None else best[2],
            evidence_credit=0 if interview or best is None or best[0] is None else min(best[0] / skill.required_evidence_level, 1),
            skill_credit=0 if interview or best is None else best[1],
            match_type=best[5] if best else "absent",
            reason="Interview-assessed; excluded from numerical scoring." if interview else best[3] if best else "No supported skill evidence found.",
            evidence=[item[4] for item in matches[:3]],
        ))
    weighted = [r for r in results if r.assessment_method == "resume"]
    score = round(100 * sum(r.importance * r.skill_credit for r in weighted) / sum(r.importance for r in weighted), 2) if weighted else None
    sections = {key:[p for p in entries if p.section == key] for key in ("projects", "education", "coursework", "experience", "internships")}
    return AnalysisResult(version=snapshot.analysis_version, model=MODEL_REPO, model_revision=MODEL_REVISION, model_file=MODEL_FILE,
                          score=score, complete=complete, skills=results, sections=sections,
                          extracted_skills=[r.skill for r in results if r.match_type == "explicit"])

"""Explicit mandatory-skill presence checks. No embedding or scoring work."""

from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import re

from app.services.pdf import normalize_text


GATE_VERSION = "mandatory-presence-v1"


@dataclass(frozen=True)
class GateRequirement:
    skill: str
    mandatory: bool = False
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        if not normalize_text(self.skill) or any(not normalize_text(alias) for alias in self.aliases):
            raise ValueError("Skill names and aliases must not be blank")


@dataclass(frozen=True)
class GateDecision:
    missing_skills: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_skills


# Check the current clause, rather than negating every later skill on a page.
# A contrast such as "no Python, but SQL" starts a new claim.
_CLAUSE_BOUNDARY = re.compile(r"[\n;]|[.!?](?=\s|$)|\b(?:but|however|although|yet)\b", re.IGNORECASE)
_NEGATION = re.compile(
    r"\b(?:no|not|without|lack(?:s|ing)?|never|"
    r"haven['’]t|hasn['’]t|hadn['’]t|didn['’]t|don['’]t|doesn['’]t|"
    r"can['’]t|cannot)\b", re.IGNORECASE,
)
_FUTURE_CLAIM = re.compile(
    r"\b(?:(?:plan(?:ning)?|want|hope|intend|aim|wish|would like|eager|keen)\s+"
    r"(?:to\s+)?(?:learn|study|explore|use)|will\s+(?:learn|study|explore))\b",
    re.IGNORECASE,
)
_NEGATIVE_SUFFIX = re.compile(
    r"^\s*(?:[:=—–-]\s*|\(\s*)?"
    r"(?:none\b|no\s+(?:experience|knowledge|exposure)\b|"
    r"not\s+(?:familiar|experienced|known|used|yet)\b)", re.IGNORECASE,
)


def _is_claim(text: str, start: int, end: int, clause_starts: list[int], negative_starts: list[int]) -> bool:
    clause_start = clause_starts[bisect_right(clause_starts, start) - 1]
    negative_index = bisect_left(negative_starts, clause_start)
    if negative_index < len(negative_starts) and negative_starts[negative_index] < start:
        return False
    # A negative suffix applies to this occurrence, not to a later list item.
    return _NEGATIVE_SUFFIX.match(text[end:end + 100]) is None


def check_mandatory_skills(text: str, requirements: tuple[GateRequirement, ...]) -> GateDecision:
    """Require an affirmative explicit name/approved alias for every mandatory skill.

    This is a versioned English-language heuristic, not proof of ability.
    Interview-assessed mandatory skills use the same presence-only gate.
    """
    text = normalize_text(text)
    # PDF line wrapping must not turn "No experience with\nPython" positive.
    # Blank lines still separate claims and independently extracted blocks.
    text = re.sub(
        r"(\b(?:with|in|of|using|learn|study|experience|knowledge|exposure|no|not)|,)"
        r"[ \t]*\n[ \t]*(?=\S)", r"\1 ", text, flags=re.IGNORECASE,
    )
    clause_starts = [0, *(match.end() for match in _CLAUSE_BOUNDARY.finditer(text))]
    # Ignore the idiom without changing the offsets of other matches.
    context = re.sub(r"\bnot\s+only\b", lambda m: " " * len(m[0]), text, flags=re.IGNORECASE)
    negative_starts = sorted(match.start() for pattern in (_NEGATION, _FUTURE_CLAIM)
                             for match in pattern.finditer(context))
    missing: list[str] = []
    for requirement in requirements:
        if not requirement.mandatory:
            continue
        terms = sorted({normalize_text(t) for t in (requirement.skill, *requirement.aliases)}, key=len, reverse=True)
        alternatives = "|".join(re.escape(term) for term in terms)
        # Protect punctuation-bearing names: C must not match C++ or C#,
        # SQL must not match NoSQL, and .NET must not match ASP.NET.
        pattern = re.compile(r"(?<![\w+#.])(?:" + alternatives + r")(?![\w+#])", re.IGNORECASE)
        if not any(_is_claim(text, match.start(), match.end(), clause_starts, negative_starts)
                   for match in pattern.finditer(text)):
            missing.append(requirement.skill)
    return GateDecision(tuple(missing))

"""Optional reporting-only competencies, kept separate from scored requirements."""
import re
from typing import Annotated

from pydantic import Field

CompetencyName = Annotated[str, Field(min_length=1, max_length=100)]


def clean_competencies(values: list[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Competencies must not be blank")
        if re.fullmatch(r"dsa|data structures?(?:\s*(?:and|&)\s*|\s+)algorithms?", value, re.I):
            raise ValueError("Add DSA under Skills & Requirements so it can be scored")
        if value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
    return result

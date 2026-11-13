"""Portable report filenames derived from the frozen assessment job title."""
import re
import unicodedata
from urllib.parse import quote


def results_filename(title: str) -> str:
    title = unicodedata.normalize("NFKC", title)
    title = "".join(" " if unicodedata.category(char).startswith("C") or char in '<>:"/\\|?*' else char for char in title)
    base = re.sub(r"\s+", " ", title).strip(" .")[:100].rstrip(" .") or "assessment"
    return f"{base}-results.csv"


def export_disposition(title: str) -> str:
    filename = results_filename(title)
    fallback_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    fallback = results_filename(fallback_title)
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'

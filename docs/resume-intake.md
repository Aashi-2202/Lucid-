# Resume intake and mandatory-skill screening

This backend stage downloads one PDF, extracts selectable text, and applies the
mandatory presence gate. It is connected to the persistent assessment worker
described in [queue/API details](assessment-queue.md). Frontend assessment
controls, evidence-level classification, embedding inference, and ranking remain
outside the current implementation.

## Entry points

- `app.services.intake.screen_drive_file`: download and screen one file from an
  already authorised job folder.
- `app.services.screening.screen_pdf`: screen PDF bytes without Drive.
- `app.services.pdf.extract_pdf`: extract original/normalized text blocks with
  one-based page numbers and bounding boxes.
- `app.services.mandatory_gate.check_mandatory_skills`: apply explicit presence
  checks without doing inference or assigning evidence levels.

Example, called by a worker after verifying that the signed-in recruiter owns
the job and is authorised to use its folder:

```python
from app.services.intake import screen_drive_file
from app.services.mandatory_gate import GateRequirement

result = screen_drive_file(
    file_id=queued_file_id,
    folder_id=job.folder_id,
    expected_version=queued_file_version,
    requirements=tuple(
        GateRequirement(s.skill, s.mandatory, tuple(s.aliases or ()))
        for s in frozen_skills
    ),
)
```

These functions are synchronous. Run them outside FastAPI's async event loop.
They do not authenticate recruiters, persist state, or modify original Drive
files. Passing an arbitrary folder ID is not an authorisation mechanism.

## Outcomes

| Status | Meaning | Retained by the result |
| --- | --- | --- |
| `ready_for_analysis` | Readable PDF; all mandatory skills explicitly present | Extracted text blocks and page references |
| `excluded` | At least one mandatory requirement lacks an affirmative match | Missing requirement names only |
| `failed` | Download or extraction could not produce a usable input | Safe error code and message |

Failures never enter the mandatory gate. Excluded results contain no extracted
candidate information, embedding analysis, score, or rank. A ready result means
only that the candidate passed this presence gate; it is not an assessment score.
The caller may retain a file identifier separately for operational tracking.

## Download and extraction rules

Downloads use the read-only service account. The file must be a non-trashed PDF
directly inside the supplied job folder; shortcuts and nested folders are not
followed. File version, folder membership, and type are checked before and after
download. A version differing from the discovered queue version fails the file
instead of silently replacing the assessment's input.

Metadata size and actual buffered bytes are both limited. Drive reads use chunks
of at most 256 KiB, with up to two retries per chunk. The HTTP client may receive a
larger response if a server ignores the range header; the buffer rejects that
response before retaining it. This is not a hard limit on transport memory.

`PdfLimits` accepts per-run limits. Initial defaults are engineering guardrails,
not measured production capacity:

| Limit | Default |
| --- | --- |
| File size | 10 MiB |
| Page count | 20 |
| Minimum extracted letters/digits | 40 |
| Maximum original extracted text length | 200,000 characters |
| Extraction time budget | 20 seconds, checked between native operations |

Encrypted files, damaged files that require structural repair, undecodable text,
and insufficient selectable text produce processing failures. A nearly textless
page whose images cover at least half the page is treated as requiring OCR,
including when other pages have selectable text. Blank trailing pages are allowed.

Image coverage and text quality are heuristics. Overlapping image areas are added,
so some unusual layouts can be conservatively rejected. Selectable headers on
otherwise scanned pages, vector-only scans, garbled fonts, multi-column reading
order, language, and extraction completeness are not fully validated. OCR is
outside this version. Retain the original text and page coordinates for later
review rather than treating normalization as proof of accurate extraction.

The extraction service's own budget is cooperative. It cannot interrupt a stuck
native parsing call, and the download service has no overall network deadline.
The assessment worker now wraps each discovery/file operation in an isolated
child process with a hard timeout covering network calls and PDF parsing.
Calling the services directly does not provide that process boundary.

## Mandatory gate rules

Gate version: `mandatory-presence-v1`.

- Match explicit names and recruiter-approved aliases, case-insensitively.
- Preserve punctuation in names such as `C++`, `C#`, `.NET`, and `Node.js`.
- Use boundaries so `SQL` does not match `NoSQL` or `SQLAlchemy`.
- Ignore common negative claims and future learning plans. A separate affirmative
  occurrence can still satisfy the gate.
- Apply the same presence rule to mandatory interview-assessed requirements.
  The gate does not use importance or required evidence level.
- Skip optional requirements. Semantic similarity never satisfies this gate.

The English clause/negation rules are a baseline. They do not understand every
conditional, quotation, negation scope, or ambiguous short skill name such as
`R` or `Go`. Validate against labelled real resumes before relying on automated
exclusions; no exclusion-accuracy or model-calibration claim has been established.

## Verification

From `backend/`, with the backend dependencies installed:

```powershell
python -W error -m unittest discover -s tests -v
```

Tests generate small PDFs in memory and mock Drive transport. They exercise the
real PyMuPDF parser and Google's chunk downloader without needing Google keys,
Neon, a model download, or real candidate data. Live Drive access, real resume
quality, hosted memory usage, and database recovery are not covered here.

## Next integration

The authenticated start/progress API, saved inputs, durable queue, and restart
recovery are implemented. Next, connect frontend assessment controls and add
structured evidence analysis, bucketed relevance, weighted scoring, and rankings.

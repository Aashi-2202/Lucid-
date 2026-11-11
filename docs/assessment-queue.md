# Assessment processing and results

Saved drafts can now initiate complete local assessments from the browser. The
same flow is available through the authenticated API. A run reads the authorised
Drive folder, processes PDFs sequentially, applies the mandatory presence gate,
analyses passing resumes, saves source-linked results, and generates a ranking.

## Local preparation

From `backend/`, install the backend dependencies and run:

```powershell
python -m app.services.embeddings
uvicorn app.main:app --port 8000
```

The preparation command downloads the public model and tokenizer to the ignored
`backend/.model-cache` directory and checks inference. It sends no resumes to
Hugging Face. Inference subsequently uses local files only. Enable
`ASSESSMENT_WORKER_ENABLED=true`; the browser checks `/assessment-engine` before
starting and reports an unavailable service rather than silently queuing work.
The API retains its ability to queue work while an operator pauses the worker.

The original Sentence Transformer model remains `all-MiniLM-L6-v2`, executed
through ONNX Runtime CPU with its tokenizer, attention-mask mean pooling and L2
normalisation. The deployment requirements omit the full `sentence-transformers`
Python wrapper and PyTorch; the exported model is executed directly by ONNX Runtime.
The pinned repository revision is
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; the artifact is
`onnx/model_quint8_avx2.onnx`. No LLM API or model-host credential is required.
See the [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
and [ONNX pooling guidance](https://sbert.net/docs/sentence_transformer/usage/efficiency.html#onnx).

The encoder batches eight texts, uses two intra-op CPU threads and truncates at
256 word pieces. Passage construction uses at most 80 words per chunk and rejects
more than 600 passages instead of silently dropping the end of a resume. These
are engineering limits, not measured Render capacity. The runtime is reused
within one PDF operation. Each PDF still gets an isolated child process, so the
model is reloaded for each PDF; cached artifacts avoid repeated downloads. This
retains killable native/network operations at a startup cost per file.

## Browser workflow

1. Save job details and all requirement settings.
2. Review the saved folder and skill summary, then select **Initiate assessment**.
3. The client checks readiness and folder access again. It retains a request UUID
   across uncertain start responses so retries return the same assessment.
4. Follow progress and separate Assessed, Excluded and Failed lists. Leave and
   reopen the saved run from Previous assessments if necessary.
5. Open a resume for evidence categories, section extraction, original PDF text,
   page references and explicit/semantic matching information.
6. Download final ranked results as CSV. Formula-like filenames are escaped.

Draft changes apply to subsequent runs. Pending unsaved edits cannot be included
silently. Requests have 30-second client timeouts; progress polls every 2.5 seconds
and pauses after three failed refreshes, retaining the last known data and a
retry action. A sleeping host can require another readiness attempt.

## Processing policy

The worker freezes the directly contained, accessible, non-trashed PDF list at
**discovery time**, following pagination. Stable order is case-folded filename
then Drive ID. Each source records ID, filename and available version/size/date
metadata. Version changes are rejected rather than substituted silently.

Extraction retains source pages and blocks. Unreadable, encrypted, damaged or
OCR-dependent files are processing failures. An individual failure does not stop
the remaining queue. Original Drive files are unchanged.

Before analysis, all mandatory names or approved aliases must be explicitly
present under the existing boundary/negation rules. Importance and evidence level
do not change this gate. Interview-assessed mandatory requirements use the same
presence check. Exclusions retain missing requirements and status, without an
extracted document or score. No embedding or evidence analysis runs for them.

For passing resumes, the versioned `resume-evidence-v1` policy:

- Detects explicit skills/coursework/education/projects/experience/internship
  sections and retains actual passages and entry context; missing facts are not invented.
- Retrieves evidence per requirement, using the requirement description or job
  context, explicit names/aliases, and the pinned Sentence Transformer.
- Assigns the highest clearly supported category: 1 mention/basic, 2 coursework,
  3 applied project, 4 internship, 5 skill application linked to a work entry
  spanning at least six months. A heading alone does not elevate a skill.
- Uses dated entry context for duration; year-only, reversed or future intervals
  cannot establish six months. `Present` uses the snapshot's frozen UTC date.
- Marks moderate semantic-only evidence undetermined with zero provisional
  credit and an incomplete assessment. Strong semantic application can support a
  category. These thresholds are initial heuristics, not validated probabilities.
- Omits interview requirements from all numeric credit and score denominators.

Default cosine thresholds 0.30, 0.50, 0.65 and 0.80 map relevance to
0, 0.25, 0.5, 0.75 and 1. Explicit matches retain at least 0.25 relevance credit.
Cosine similarity is never presented as confidence or proficiency.

```text
Evidence credit = min(supported evidence level / required evidence level, 1)
Skill credit = relevance bucket × evidence credit
Score = 100 × sum(importance × skill credit) / sum(resume-assessed importance)
```

Absent optional skills and undetermined evidence retain their weights with zero
credit. Scores round to two decimal places before ranking. Equal scores share a
competition rank. All passing resumes are ranked together; early results are
provisional. All-interview configurations have no numeric score or rank.

## API and compatibility

All endpoints require an approved recruiter and enforce ownership. Another
recruiter's job/run returns 404; file details are scoped to the owned run.

| Endpoint | Purpose |
| --- | --- |
| `GET /assessment-engine` | Local model-cache and worker readiness |
| `POST /jobs/{id}/assessments` | Start; JSON `idempotency_key` is a UUID; returns 202 and Location |
| `GET /jobs/{id}/assessments` | Saved run history, limit/offset pagination |
| `GET /assessments/{id}` | Phase, counts, current filename, run-level error |
| `GET /assessments/{id}/snapshot` | Frozen requirements, model revision/file, rubric, date and limits |
| `GET /assessments/{id}/files` | Frozen file outcomes, limit/offset and optional status |
| `GET /assessments/{id}/files/{file_id}` | Original extracted document and analysis, only for passing files |
| `GET /assessments/{id}/results` | Ordered result rows, tied ranks and provisional flag |
| `GET /assessments/{id}/export` | Final CSV; active runs return 409 |

The existing schema is retained. Analysis lives in the document JSON alongside
original blocks. Storage uses the previous terminal `screened` run state and
`ready_for_analysis` file state. New analysis-enabled runs are exposed as
`completed` by the API once all passing files contain analysis. The compatibility
`ready_for_analysis` count includes analysed files; `assessed` is the count with
analysis. Older intake-only snapshots remain `screened` and have no ranked
results; start a new run to analyse them. No migration fabricates old scores.

## Recovery, isolation and bounds

The existing unique active-slot constraint permits one active assessment across
the deployment. Conditional database updates acquire a token and an expiry using
database time; no transaction stays open while Drive/PDF/model work runs. The
lease is the saved per-file timeout plus 30 seconds. A write is accepted only
while its token matches and its lease has not expired.

Discovery and each PDF operation run in killable child processes. The parent
kills/reaps timed-out children and bounds protocol input/output at 4 MiB. A model
failure produces a file failure, never a fabricated zero-score success. Worker
stderr is discarded, and logs omit resume content and SQL parameters.

Outcomes and final transitions commit together. Completed files are not selected
again. After a crash, unfinished work can run again after lease expiry; this is
at-least-once external reading with one accepted checkpoint. Clean shutdown
kills/reaps the child and releases its lease. Unclean parent termination may leave
a read-only orphan until the host cleans up its process group; fencing prevents
stale database writes.

| Setting | Default |
| --- | --- |
| `ASSESSMENT_WORKER_ENABLED` | true |
| `ASSESSMENT_POLL_SECONDS` | 2 |
| `ASSESSMENT_FILE_TIMEOUT_SECONDS` | 60 |
| `ASSESSMENT_MAX_FILES` | 100 |

Python 3.11+ is required. Windows selector loops dispatch subprocess operations
through a dedicated Proactor loop. Existing asyncpg URLs use `?ssl=require`.

## Verification and limits

121 backend tests passed with warnings treated as errors. They cover the existing
queue/gate controls and synthetic labelled rubric cases, score calculation,
interview exclusion, unknown evidence, tie handling, exports, ownership and old
snapshot compatibility. Model downloads are not required for this test suite.

A separate live run used actual Drive downloads, the pinned ONNX model, the running
HTTP API and Neon development persistence: 5 processed, 4 analysed, 1 OCR failure,
with repeated-start and CSV checks. The user also launched their configured job
through Chrome: 1 analysed, 3 mandatory exclusions, 1 failure. See the
[live report](live-verification-2026-11-12.md).

Manual parser corrections/reassessment, calibration on a manually labelled real
resume dataset, broader layout/negation coverage, and hosted memory/cold-start
measurement remain outstanding. These results establish local operation, not
hiring accuracy or verified candidate competence. OCR, continuous monitoring and
the detailed explanation dashboard remain deferred.

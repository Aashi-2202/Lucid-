# Persistent intake assessments

The backend can start an assessment, discover its Google Drive PDFs, process them
one at a time, checkpoint each outcome, and resume unfinished work after a
restart. This completes intake and mandatory-skill screening. It does not yet
assign evidence levels, run the embedding model, calculate scores, or rank people.

## Start and inspect a run

Use an approved recruiter's Bearer session token. The endpoints are also available
through Swagger at `/docs`.

```http
POST /jobs/1/assessments
Authorization: Bearer <session-token>
Content-Type: application/json

{"idempotency_key":"773f9bde-8ec7-49b7-91db-d32e6bda8617"}
```

The response is `202 Accepted`, with an assessment ID, progress fields, and a
`Location: /assessments/<id>` header. The request does database work only; Drive
discovery starts asynchronously. At first, `phase` is `discovery` and
`total_files` is `null`.

Generate a fresh UUID for each intended run. Reuse the same key when retrying a
request: the original assessment is returned, including after it finishes. Reusing
that key for another job is a conflict. At most one assessment is active across
the deployment; a distinct start while it is busy returns `409`.

| Endpoint | Result |
| --- | --- |
| `GET /jobs/{job_id}/assessments` | Recent runs for the owning recruiter; `limit` and `offset` pagination |
| `GET /assessments/{id}` | Phase, counts, current filename, and any run-level error |
| `GET /assessments/{id}/snapshot` | Saved job, requirements, limits, and versioned policy inputs |
| `GET /assessments/{id}/files` | File outcomes in frozen queue order; `limit`, `offset`, optional `status` |
| `GET /assessments/{id}/files/{file_id}` | One file's outcome, Drive ID/version, and extracted text only if ready |

All endpoints verify account approval and ownership. Other recruiters receive
`404` for an assessment or job they do not own. File details are also scoped to
the assessment, so a file ID from another run cannot cross that boundary.

Poll progress every few seconds. The counts distinguish `ready_for_analysis`,
`excluded`, and `failed`; their sum is `processed_files`. File lists omit extracted
text. The detail endpoint returns no extracted document for an exclusion/failure.

## States and saved inputs

Runs move through `queued` → `running` → `screened`, or terminal `failed` for a
run-level problem such as an inaccessible/empty source folder. `phase` distinguishes
discovery from screening while a run is active.

`screened` means intake finished, including any per-file failures. It does not
mean all files succeeded or that ranking has been completed. Individual files
move from `pending` to exactly one of `ready_for_analysis`, `excluded`, or `failed`.
An individual failure does not stop the remaining files.

At initiation, a single database query captures the job and skill settings. The
saved snapshot includes descriptions, aliases, mandatory flags, importance,
required evidence levels, assessment methods, intake/gate schema versions, PDF
limits, per-file timeout, file cap, embedding model name, and relevance thresholds.
The latter two are reserved inputs for the future analysis stage, not evidence
that model inference has run. Draft edits do not alter an existing run.

The worker validates access again during discovery. It freezes the direct,
non-trashed PDF list at **discovery time**, rather than at the instant the POST
arrives. Files added afterward belong to a later run. Queue order is stable by
case-folded filename and Drive ID. Every entry saves its ID, name, version, size,
and modification time when available. Downloads reject changed versions rather
than silently substituting newer contents.

## Persistence, sequential execution, and recovery

`assessments` and `assessment_files` are additive tables created by the existing
startup table-creation step. Existing PostgreSQL skill alias storage stays an
array; its SQLite JSON variant exists for local integration tests. The application
still needs an external PostgreSQL database such as Neon for deployed persistence.

A unique active-slot constraint prevents two active runs, even when start requests
race. Workers acquire the active run using one conditional `UPDATE ... RETURNING`.
Each claim gets a random token and an expiry based on database time. The lease is
the saved per-file timeout plus 30 seconds. No database transaction stays open
while Drive/PDF work runs.

A result is committed only if its claim token still matches and its lease has
not expired. The file outcome and any final run-state transition commit together.
An expired/late worker cannot overwrite a replacement's result. Completed files
are never selected again. Unfinished work may be executed again after a crash;
this is at-least-once processing with one accepted checkpoint, not exactly-once
execution of external reads.

Clean shutdown kills/reaps the current child and releases its lease. After an
unclean interruption, a new worker waits for the saved lease to expire, then
retries the unfinished operation. With defaults, that wait is at most roughly
90 seconds plus a poll interval after the last claim. Database outages can extend
recovery. An abrupt parent-process kill can leave an orphaned read-only child
until the host cleans up its process group; fencing still prevents stale writes.

## Isolation and settings

Each folder-discovery/file operation runs in a separate child process. The parent
enforces a timeout after child creation, kills/reaps an overlong operation, and
records `processing_timeout`. Input/output JSON is capped at 4 MiB. Worker stderr
is discarded and queue errors do not log SQL parameters or resume contents.

The child uses the backend's working directory and credentials configuration.
On Windows selector loops, subprocess work uses a dedicated Proactor loop while
preserving the server's own loop policy. Python 3.11 or newer is required.

| Setting | Default | Purpose |
| --- | --- | --- |
| `ASSESSMENT_WORKER_ENABLED` | `true` | Start the queue consumer in API lifespan |
| `ASSESSMENT_POLL_SECONDS` | `2` | Idle/retry interval |
| `ASSESSMENT_FILE_TIMEOUT_SECONDS` | `60` | Discovery or one-file processing budget |
| `ASSESSMENT_MAX_FILES` | `100` | Maximum PDFs admitted during discovery |

These are engineering guardrails, not measured Render capacity. Timeout/cap values
are saved per run; changing them affects new runs. Setting the worker flag false
leaves queued work saved but unprocessed. Keep one API process for the initial MVP
and initial schema creation; concurrent worker claims are guarded in the database.

For this project's asyncpg connection URL, use
`postgresql+asyncpg://user:password@host/db?ssl=require`.
The previous `sslmode` example was a libpq-style option that asyncpg does not accept
as a connection keyword. Use the actual host, database, and URL-encoded credentials
from Neon; keep secrets in the backend environment.

## Verification and remaining integration

From `backend/`:

```powershell
pip install -r requirements-test.txt
python -W error -m unittest discover -s tests -v
```

The suite uses an on-disk SQLite test database with foreign keys enabled. It covers
HTTP authentication/ownership, idempotency and competing requests, sequential
checkpoints, reopening the database, expired leases/stale commits, snapshot
stability, and shutdown. It also exercises real child-process protocol handling,
timeouts, oversized output, and cancellation under both Windows event-loop types.
PDF/Drive tests use synthetic files and mocked transport; a real child is also
tested with deliberately missing credentials.

Live Neon/PostgreSQL concurrency, live Drive access, and deployed memory/cold-start
behavior remain unverified. The next integration is frontend start/progress
controls, followed by evidence classification, semantic relevance, weighted
scoring, and final ranked results.

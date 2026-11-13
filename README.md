# Lucid

AI-powered resume screening tool for recruiters.

## Architecture

```
frontend/    → React + TypeScript (Render Static Site)
backend/     → Python + FastAPI (Render Free Web Service)
Database     → Neon PostgreSQL (cloud)
File Storage → Client's Google Drive (read-only via service account)
```

## Local Development

### Backend

Use Python 3.11 or newer.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
python -m app.core.migrate  # Initialize tables / apply account and competency upgrades
python -m app.services.embeddings  # Download and check the pinned ONNX model once
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`, backend on `http://localhost:8000`.

### Google sign-in configuration

Copy each app's `.env.example` to `.env`. Set `GOOGLE_CLIENT_ID` in the
backend and `VITE_GOOGLE_CLIENT_ID` in the frontend to the same Google OAuth
**Web application** client ID. Register `http://localhost:5173` as an authorized
JavaScript origin. This button uses a JavaScript callback, so it does not need
a redirect URI. Keep `VITE_API_URL=/api` locally so Vite forwards requests to
the backend. Restart both servers after changing environment variables.

`ALLOW_PUBLIC_SIGNUP=true` is the default: any verified Google account can
register and sign in immediately. Accounts previously waiting for approval are
approved on their next successful Google sign-in. Each recruiter can access only
their own jobs and assessments.

For administrator approval instead, set `ALLOW_PUBLIC_SIGNUP=false`. In that
mode, `APPROVED_RECRUITER_EMAILS` is a JSON array of emails to approve on first
registration, such as `["recruiter@example.com"]`; existing unapproved accounts
stay unapproved. Changing this setting does not revoke already approved accounts.
Keep the actual email list, database URL, service-account key, and JWT secret in ignored local
configuration. A client ID can be public; a client secret is not used by this
sign-in flow. Test real Google sign-in in your regular browser.

You can also choose **Create account** to use a username and password without a
Google sign-in. New accounts link a Gmail address using a six-digit email code;
passwords require 8–128 characters and at least one special character. Configure
the backend SMTP sender before enabling this flow. Passwords use Argon2id hashes.
Upgrade an existing database
with `python -m app.core.migrate` before starting this version; existing Google
accounts/jobs are preserved. Password recovery and account linking are not yet
implemented. See [local accounts](docs/local-accounts.md).

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | Python + FastAPI |
| PDF Extraction | PyMuPDF |
| Semantic Retrieval | Sentence Transformers (ONNX Runtime) |
| Scoring | Deterministic Python + versioned config |
| Database | Neon PostgreSQL |
| Auth | Google Identity Services or username/password; Argon2id; signed JWT sessions |
| File Access | Google Drive API (service account) |

## Current implementation

The [product requirements](docs/product-requirements.md) reconcile the agreed
workflow with the current stack and distinguish completed features from pending work.

- Google or username/password sign-up/sign-in, optional administrator approval,
  and signed session tokens. New username accounts require Gmail verification;
  legacy accounts keep working. See
  [account setup and security details](docs/local-accounts.md).
- Job drafts, Drive folder access checks, and configurable skill requirements.
- Optional Additional competencies: communication, leadership/influence, problem
  solving/critical thinking, learning agility, and custom nontechnical names.
  These supply reporting signals only, without scores or exclusions.
- Delete owned jobs and their saved assessments/results from the Jobs list after
  confirmation. Queued/running assessments block deletion; Drive originals stay unchanged.
- All seven requirement controls are available before creating a job: suggested
  or custom skills, description, mandatory checkbox, importance, evidence level,
  assessment method, and expandable approved aliases. Job details and requirements
  save together. Interview requirements retain Mandatory and hide scoring sliders.
- Backend services for bounded PDF downloads, text extraction with page
  references, and mandatory-skill presence screening.
- Persistent assessment queue, frozen job/skill inputs, sequential intake,
  per-file checkpoints, restart recovery, and authenticated progress APIs.

- Initiate assessments from the saved job, recheck folder access, follow live
  progress, reopen previous runs, and view separate assessed/excluded/failed lists.
- Section-based evidence categories, pinned Sentence Transformer ONNX passage
  retrieval, weighted evidence-fulfilment scores, tied ranks, source passages,
  and CSV export. Interview requirements remain unscored.
- New assessments include a **Job Match Summary** CSV column: brief technical
  evidence alignment/gaps and requested additional competencies, without resume
  quotations. Older assessments keep their saved scores and have no fabricated
  summaries. See [competency reporting](docs/additional-competencies.md).

After saving job settings, scroll below the folder section and select
**Initiate assessment**. The local backend needs `ASSESSMENT_WORKER_ENABLED=true`
and the model cache prepared with the command above. No model-host API key is
required; resume inference runs locally. The `.model-cache` directory is ignored
by Git. Keep one backend process initially. See [assessment details](docs/assessment-queue.md)
and [resume intake details](docs/resume-intake.md).

The deployment dependencies intentionally omit PyTorch and the full
`sentence-transformers` Python package. The pretrained Sentence Transformer is
executed directly using ONNX Runtime, its tokenizer and NumPy pooling.

## Backend tests

For a test environment without embedding-model packages, run from `backend/`:

```powershell
pip install -r requirements-test.txt
python -W error -m unittest discover -s tests -v
```

Tests use a temporary on-disk SQLite database, generated PDFs, mocked Drive
transport, and real isolated child processes. Google credentials, Neon, and model
downloads are not required.

Frontend requirement-draft tests run with `cd frontend; npm test` using Node
22.18+ (Node 24 used for verification), without extra test dependencies.

Live Drive/Neon intake verification completed on 12 November 2026: 5 PDFs
processed, 4 ready for analysis, 1 flagged as requiring OCR, with saved progress
recovered in a fresh worker process. See the [verification report](docs/live-verification-2026-11-12.md)
for what was exercised and what remains pending. Local Google sign-in was also
verified: the user reached the Jobs page, and the approved account was confirmed
in Neon. A subsequent live run completed ONNX evidence analysis on 4 of 5 PDFs and
verified saved scores and CSV export. The user also initiated an assessment
through the real browser: 1 assessed, 3 excluded, 1 failed. Hosted behavior,
manual parser corrections, and calibration on a labelled real-resume dataset
remain outstanding.

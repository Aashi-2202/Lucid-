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
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`, backend on `http://localhost:8000`.

## Tech Stack

| Component | Technology |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | Python + FastAPI |
| PDF Extraction | PyMuPDF |
| Semantic Retrieval | Sentence Transformers (ONNX Runtime) |
| Scoring | Deterministic Python + versioned config |
| Database | Neon PostgreSQL |
| Auth | Google Identity Services |
| File Access | Google Drive API (service account) |

## Current implementation

- Google sign-in, approved recruiter accounts, and signed session tokens.
- Job drafts, Drive folder access checks, and configurable skill requirements.
- Backend services for bounded PDF downloads, text extraction with page
  references, and mandatory-skill presence screening.
- Persistent assessment queue, frozen job/skill inputs, sequential intake,
  per-file checkpoints, restart recovery, and authenticated progress APIs.

Assessments can now be initiated and inspected through the API, including
Swagger at `/docs`. The frontend assessment controls, evidence analysis, and
ranking are the next integration steps. See [queue/API details](docs/assessment-queue.md)
and [resume intake details](docs/resume-intake.md) for usage and verification.

## Backend tests

For a test environment without embedding-model packages, run from `backend/`:

```powershell
pip install -r requirements-test.txt
python -W error -m unittest discover -s tests -v
```

Tests use a temporary on-disk SQLite database, generated PDFs, mocked Drive
transport, and real isolated child processes. Google credentials, Neon, and model
downloads are not required.

Live Drive/Neon intake verification completed on 12 November 2026: 5 PDFs
processed, 4 ready for analysis, 1 flagged as requiring OCR, with saved progress
recovered in a fresh worker process. See the [verification report](docs/live-verification-2026-11-12.md)
for what was exercised and what remains pending, including Google OAuth sign-in.

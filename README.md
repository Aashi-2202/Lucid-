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

Resume intake is currently a tested service layer. Starting assessments from
the app, persistent processing/progress, evidence analysis, and ranking are the
next integration steps. See [resume intake details](docs/resume-intake.md) for
outcomes, limits, usage, and verification.

## Backend tests

After installing the backend dependencies, run from `backend/`:

```powershell
python -W error -m unittest discover -s tests -v
```

The tests use generated PDFs and mocked Drive transport; Google credentials,
Neon, and model downloads are not required.

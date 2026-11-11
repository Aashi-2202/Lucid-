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

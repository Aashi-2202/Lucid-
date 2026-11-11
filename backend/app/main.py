from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title="Lucid API",
    description="AI-powered resume screening backend",
    version="0.1.0",
)

# CORS — allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Readiness probe — frontend calls this to wake the backend."""
    return {"status": "ok", "version": "0.1.0"}

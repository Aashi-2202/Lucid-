from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_tables
from app.routes.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Create tables on startup (MVP — migrate to Alembic later)
    await create_tables()
    yield


app = FastAPI(
    title="Lucid API",
    description="AI-powered resume screening backend",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)


@app.get("/health")
async def health_check():
    """Readiness probe — frontend calls this to wake the backend."""
    return {"status": "ok", "version": "0.1.0"}

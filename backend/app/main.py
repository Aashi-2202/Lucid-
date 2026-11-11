import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_tables, async_session, engine
from app.routes.auth import router as auth_router
from app.routes.jobs import router as jobs_router
from app.routes.assessments import router as assessments_router
from app.services.assessment_queue import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Create tables on startup (MVP — migrate to Alembic later)
    await create_tables()
    worker = asyncio.create_task(worker_loop(async_session, settings.assessment_poll_seconds)) if settings.assessment_worker_enabled else None
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await engine.dispose()


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
app.include_router(jobs_router)
app.include_router(assessments_router)


@app.get("/health")
async def health_check():
    """Readiness probe — frontend calls this to wake the backend."""
    return {"status": "ok", "version": "0.1.0"}

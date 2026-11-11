from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://user:pass@localhost/lucid"

    # Google OAuth
    google_client_id: str = ""

    # Google Drive service account
    google_service_account_file: str = ""

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173"]

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480  # 8 hours

    # Model
    embedding_model: str = "all-MiniLM-L6-v2"

    # Relevance buckets (cosine similarity thresholds)
    relevance_bucket_none: float = 0.30
    relevance_bucket_weak: float = 0.50
    relevance_bucket_moderate: float = 0.65
    relevance_bucket_strong: float = 0.80

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

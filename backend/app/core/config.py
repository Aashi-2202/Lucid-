from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://user:pass@localhost/lucid"
    database_direct_url: str = ""  # Optional explicit migration connection.

    # Google OAuth
    google_client_id: str = ""
    # Google-verified and username/password accounts may register without approval.
    allow_public_signup: bool = True
    # Auto-approve newly registered, Google-verified accounts listed here.
    approved_recruiter_emails: list[str] = Field(default_factory=list)

    # Google Drive service account
    google_service_account_file: str = ""

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173"]

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480  # 8 hours

    # Verification email delivery. Never expose credentials to the frontend.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = ""

    # Model
    embedding_model: str = "all-MiniLM-L6-v2"

    # Intake queue. Capacity limits are guardrails, not measured host capacity.
    assessment_worker_enabled: bool = True
    assessment_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    assessment_file_timeout_seconds: float = Field(default=60.0, ge=1, le=600)
    assessment_max_files: int = Field(default=100, ge=1, le=1000)

    # Relevance buckets (cosine similarity thresholds)
    relevance_bucket_none: float = 0.30
    relevance_bucket_weak: float = 0.50
    relevance_bucket_moderate: float = 0.65
    relevance_bucket_strong: float = 0.80

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

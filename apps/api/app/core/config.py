from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_repo_root() -> Path | None:
    """Return the monorepo root when this package is running from a checkout.

    The API image only contains ``apps/api``, so container startup uses environment
    variables and does not require the repository root.
    """

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "compose.yaml").is_file() and (parent / "apps").is_dir():
            return parent
    return None


REPO_ROOT = find_repo_root()
ENV_FILE = REPO_ROOT / ".env" if REPO_ROOT is not None else None
_LOCAL_SMTP_HOSTS = frozenset({"127.0.0.1", "localhost", "mailpit", "::1"})


def _local_smtp_host(host: str) -> bool:
    return host.strip().lower() in _LOCAL_SMTP_HOSTS


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment and the repo `.env` file."""

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=ENV_FILE if ENV_FILE is not None and ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    secret_key: str
    database_url: str
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    cookie_secure: bool = False
    session_cookie_name: str = "atlas_session"
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    log_level: str = "INFO"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    max_cosine_distance: float = Field(default=0.55, ge=0, le=2)
    max_upload_bytes: int = Field(default=10_485_760, ge=1, le=52_428_800)
    storage_dir: str = ""
    approval_ttl_hours: int = Field(default=24, ge=1, le=168)
    public_api_url: str = "http://host.docker.internal:8000"
    n8n_lead_webhook_url: str = ""
    n8n_timeout_seconds: float = Field(default=5, ge=0.2, le=30)
    email_mode: Literal["sandbox", "live"] = "sandbox"
    email_live_enabled: bool = False
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from: str = "atlas@localhost"
    smtp_timeout_seconds: float = Field(default=5, ge=0.2, le=60)
    calendar_mode: Literal["simulation"] = "simulation"
    webhook_max_bytes: int = Field(default=65_536, ge=32, le=1_048_576)
    webhook_skew_seconds: int = Field(default=300, ge=30, le=3600)
    webhook_rate_limit: int = Field(default=30, ge=1, le=300)

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("ATLAS_DATABASE_URL must be a PostgreSQL URL")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def embedding_dimensions_match_schema(cls, value: int) -> int:
        if value != 1536:
            raise ValueError("ATLAS_EMBEDDING_DIMENSIONS must be 1536 for the current schema")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"ATLAS_LOG_LEVEL must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Self:
        if len(self.secret_key) < 32:
            raise ValueError("ATLAS_SECRET_KEY must be at least 32 characters")
        if self.environment == "production":
            if "replace-with" in self.secret_key or self.secret_key.startswith("dev-only"):
                raise ValueError("ATLAS_SECRET_KEY placeholder is not allowed in production")
            if not self.cookie_secure:
                raise ValueError("ATLAS_COOKIE_SECURE must be true in production")
        if self.email_mode == "live" and not self.email_live_enabled:
            raise ValueError("ATLAS_EMAIL_LIVE_ENABLED must be true when ATLAS_EMAIL_MODE is live")
        if self.email_mode == "sandbox" and not _local_smtp_host(self.smtp_host):
            raise ValueError("ATLAS_SMTP_HOST must be local while email mode is sandbox")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_max_age_seconds(self) -> int:
        return self.session_ttl_hours * 60 * 60

    @property
    def upload_storage_dir(self) -> Path:
        if self.storage_dir.strip():
            return Path(self.storage_dir).expanduser()
        if REPO_ROOT is not None:
            return REPO_ROOT / "var" / "atlas-storage"
        return Path("var") / "atlas-storage"


@lru_cache
def get_settings() -> Settings:
    return Settings()

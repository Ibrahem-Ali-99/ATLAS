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

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("ATLAS_DATABASE_URL must be a PostgreSQL URL")
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
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_max_age_seconds(self) -> int:
        return self.session_ttl_hours * 60 * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()

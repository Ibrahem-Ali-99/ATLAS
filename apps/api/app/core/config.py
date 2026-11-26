import os
import re
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


def _placeholder_secret(value: str) -> bool:
    lowered = value.lower()
    markers = ("replace-with", "dev-only", "change-me", "changeme")
    return any(marker in lowered for marker in markers)


def _local_smtp_host(host: str) -> bool:
    return host.strip().lower() in _LOCAL_SMTP_HOSTS


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment and the repo `.env` file."""

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=ENV_FILE if ENV_FILE is not None and ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    public_demo: bool = False
    # Empty defaults keep the type checker aligned with BaseSettings while the
    # validators still fail closed when required environment values are absent.
    secret_key: str = ""
    # Credential encryption is independently rotatable from the session key.
    # ``credential_encryption_keys`` accepts comma-separated ``key_id=value``
    # entries; the first entry is used for new seals.
    credential_encryption_keys: str = ""
    database_url: str = ""
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    cookie_secure: bool = False
    session_cookie_name: str = "atlas_session"
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    log_level: str = "INFO"
    llm_provider: Literal["openai", "groq", "double"] = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=120, ge=1, le=300)
    llm_max_output_tokens: int | None = Field(default=None, ge=1, le=32768)
    embedding_provider: Literal["openai", "ollama", "double"] = "openai"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_timeout_seconds: float = Field(default=60, ge=1, le=180)
    max_cosine_distance: float = Field(default=0.55, ge=0, le=2)
    rag_vector_only_max_distance: float = Field(default=0.45, ge=0, le=2)
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
    smtp_live_hosts: str = ""
    calendar_mode: Literal["simulation"] = "simulation"
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_redirect_uri: str = ""
    google_calendar_web_origin: str = ""
    webhook_max_bytes: int = Field(default=65_536, ge=32, le=1_048_576)
    webhook_skew_seconds: int = Field(default=300, ge=30, le=3600)
    webhook_rate_limit: int = Field(default=30, ge=1, le=300)
    login_email_limit: int = Field(default=8, ge=1, le=50)
    login_client_limit: int = Field(default=40, ge=1, le=500)
    login_window_seconds: int = Field(default=900, ge=60, le=86_400)
    model_dir: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
    llm_input_usd_per_million: float | None = None
    llm_output_usd_per_million: float | None = None
    # Empty uses the active virtualenv interpreter. An explicit path is checked at startup.
    mcp_python: str = ""
    billing_provider: Literal["sandbox", "stripe"] = "sandbox"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_ids: str = ""
    billing_public_url: str = ""
    campaign_public_url: str = ""
    campaign_link_secret: str = ""
    campaign_live_enabled: bool = False
    resend_campaign_webhook_secret: str = ""
    inbox_webhook_secret: str = ""
    whatsapp_webhook_verify_token: str = ""
    whatsapp_webhook_app_secret: str = ""
    whatsapp_live_enabled: bool = False

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("ATLAS_DATABASE_URL must be a PostgreSQL URL")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def embedding_dimensions_match_schema(cls, value: int) -> int:
        if value not in {768, 1536}:
            raise ValueError("ATLAS_EMBEDDING_DIMENSIONS must be 768 or 1536")
        return value

    @field_validator("llm_max_output_tokens", mode="before")
    @classmethod
    def empty_token_limit_is_unset(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("llm_input_usd_per_million", "llm_output_usd_per_million", mode="before")
    @classmethod
    def empty_price_is_unavailable(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("mcp_python")
    @classmethod
    def mcp_python_must_exist(cls, value: str) -> str:
        configured = value.strip()
        if not configured:
            return ""
        if not Path(configured).is_file():
            raise ValueError("ATLAS_MCP_PYTHON must be an existing executable")
        return configured

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
        if self.environment == "production" and _placeholder_secret(self.secret_key):
            raise ValueError("ATLAS_SECRET_KEY placeholder is not allowed in production")
        if self.environment == "production":
            key_ids: set[str] = set()
            for entry in self.credential_encryption_keys.split(","):
                key_id, _, key = entry.partition("=")
                if (
                    not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id)
                    or key_id in key_ids
                    or key_id == "legacy-secret-key"
                    or len(key.strip()) < 32
                    or key == self.secret_key
                    or _placeholder_secret(key)
                ):
                    raise ValueError(
                        "ATLAS_CREDENTIAL_ENCRYPTION_KEYS requires distinct key IDs and "
                        "independent, random secrets in production"
                    )
                key_ids.add(key_id)
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("ATLAS_COOKIE_SECURE must be true in production")
        if self.email_mode == "live" and not self.email_live_enabled:
            raise ValueError("ATLAS_EMAIL_LIVE_ENABLED must be true when ATLAS_EMAIL_MODE is live")
        if self.email_mode == "sandbox" and not _local_smtp_host(self.smtp_host):
            raise ValueError("ATLAS_SMTP_HOST must be local while email mode is sandbox")
        if self.environment == "production" and (
            self.llm_provider == "double" or self.embedding_provider == "double"
        ):
            raise ValueError("Deterministic providers are not allowed in production")
        if self.public_demo:
            if self.email_mode != "sandbox" or self.email_live_enabled:
                raise ValueError("ATLAS_PUBLIC_DEMO cannot send live email")
            if self.n8n_lead_webhook_url.strip():
                raise ValueError("ATLAS_PUBLIC_DEMO cannot call n8n")
            if self.llm_api_key.strip() or self.embedding_api_key.strip():
                raise ValueError("ATLAS_PUBLIC_DEMO cannot store a paid model key")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_max_age_seconds(self) -> int:
        return self.session_ttl_hours * 60 * 60

    @property
    def model_storage_dir(self) -> Path:
        if self.model_dir.strip():
            return Path(self.model_dir).expanduser()
        if REPO_ROOT is not None:
            return REPO_ROOT / "var" / "atlas-models"
        return Path("var") / "atlas-models"

    @property
    def upload_storage_dir(self) -> Path:
        if self.storage_dir.strip():
            return Path(self.storage_dir).expanduser()
        if REPO_ROOT is not None:
            return REPO_ROOT / "var" / "atlas-storage"
        return Path("var") / "atlas-storage"


@lru_cache
def get_settings() -> Settings:
    if os.environ.get("ATLAS_MCP_ISOLATED_SETTINGS") == "1":
        return Settings(_env_file=None)
    return Settings()

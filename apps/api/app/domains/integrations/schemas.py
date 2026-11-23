from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.integrations.models import IntegrationStatus, IntegrationType

SUPPORTED_PROVIDERS: dict[IntegrationType, frozenset[str]] = {
    IntegrationType.chat: frozenset({"groq", "openai"}),
    IntegrationType.embedding: frozenset({"ollama", "openai"}),
    IntegrationType.n8n: frozenset({"n8n"}),
    IntegrationType.email: frozenset({"smtp"}),
}


class IntegrationInput(BaseModel):
    integration_type: IntegrationType
    provider: str
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: str | None = Field(default=None, min_length=1)

    @field_validator("provider")
    @classmethod
    def provider_is_supported(cls, value: str) -> str:
        return value.strip().lower()

    def validate_provider(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS[self.integration_type]:
            raise ValueError(
                f"Provider {self.provider!r} is not supported for {self.integration_type.value}"
            )
        if self.integration_type == IntegrationType.email:
            host = self.config.get("host")
            port = self.config.get("port")
            from_address = self.config.get("from_address")
            if not isinstance(host, str) or not host.strip():
                raise ValueError("Email SMTP host is required")
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
                raise ValueError("Email SMTP port must be between 1 and 65535")
            if not isinstance(from_address, str) or "@" not in from_address:
                raise ValueError("Email sender address is invalid")
            if self.config.get("use_tls") and self.config.get("starttls"):
                raise ValueError("SMTP SSL and STARTTLS cannot both be enabled")


class IntegrationUpdate(BaseModel):
    provider: str
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: str | None = Field(default=None, min_length=1)
    expected_version: int | None = Field(default=None, ge=1)


class CredentialUpdate(BaseModel):
    credentials: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class VersionUpdate(BaseModel):
    expected_version: int = Field(ge=1)


class IntegrationMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    integration_type: IntegrationType
    provider: str
    config: dict[str, Any]
    status: IntegrationStatus
    credential_version: int
    has_credentials: bool
    created_at: Any
    updated_at: Any
    verified_at: Any | None = None
    verification_detail: str | None = None


class VerificationResult(BaseModel):
    integration: IntegrationMetadata
    verified: bool
    detail: str


class EmailDomainInput(BaseModel):
    domain: str = Field(min_length=3, max_length=253)


class EmailDomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    provider: str
    domain: str
    status: str
    dns_records: list[dict[str, Any]]
    verified_at: Any | None = None
    checked_at: Any | None = None

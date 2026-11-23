from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.integrations.models import IntegrationStatus, IntegrationType

SUPPORTED_PROVIDERS: dict[IntegrationType, frozenset[str]] = {
    IntegrationType.chat: frozenset({"groq", "openai"}),
    IntegrationType.embedding: frozenset({"ollama", "openai"}),
    IntegrationType.n8n: frozenset({"n8n"}),
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


class VerificationResult(BaseModel):
    integration: IntegrationMetadata
    verified: bool
    detail: str

"""Build an embedding index in bounded batches, then activate it atomically."""

import hashlib
import math
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import Text, and_, cast, delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.knowledge.models import Chunk
from app.domains.knowledge.reindex_models import EmbeddingReindex, ReindexVector
from app.domains.knowledge.vectors import index_identity, lock_embedding_index
from app.integrations.language import OpenAICompatibleEmbeddingClient

_BATCH_SIZE = 16


class ReindexRequest(BaseModel):
    provider: Literal["openai", "ollama"]
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    dimensions: Literal[768, 1536]
    credentials: SecretStr | None = None
    expected_version: int | None = Field(default=None, ge=1)


def _active(
    db: Session, organization_id: uuid.UUID, *, lock: bool = False
) -> IntegrationConfig | None:
    statement = (
        select(IntegrationConfig)
        .where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.embedding,
        )
        .execution_options(populate_existing=True)
    )
    return db.scalar(statement.with_for_update() if lock else statement)


def _revision(active: IntegrationConfig | None) -> dict[str, Any]:
    if active is None:
        return {"deployment": list(index_identity(get_settings()))}
    return {
        "id": str(active.id),
        "version": active.credential_version,
        "status": active.status.value,
    }


def start(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, body: ReindexRequest
) -> EmbeddingReindex:
    request_lock = int.from_bytes(
        hashlib.sha256(b"reindex-request:" + organization_id.bytes).digest()[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": request_lock})
    job = db.get(EmbeddingReindex, organization_id, with_for_update=True)
    lock_embedding_index(db, organization_id)
    if job and job.status == "building":
        raise AppError(409, "reindex_in_progress", "A new index is already being built")
    active = _active(db, organization_id, lock=True)
    if body.expected_version != (active.credential_version if active else None):
        raise AppError(
            409, "integration_version_conflict", "Reload the embedding provider settings"
        )
    settings = get_settings()
    base_url = body.base_url.strip().rstrip("/")
    model = body.model.strip()
    trusted = {settings.embedding_base_url.rstrip("/"), "https://api.openai.com/v1"}
    if active and isinstance(active.config.get("base_url"), str):
        trusted.add(active.config["base_url"].strip().rstrip("/"))
    if settings.public_demo or base_url not in trusted or not model:
        raise AppError(
            422, "reindex_provider_invalid", "Use a trusted embedding endpoint and model"
        )
    supplied = body.credentials.get_secret_value().strip() if body.credentials else ""
    token = seal_integration_secret(supplied) if supplied else None
    if not token:
        if (
            active
            and active.provider == body.provider
            and base_url
            == str(active.config.get("base_url", settings.embedding_base_url)).strip().rstrip("/")
        ):
            token = active.encrypted_credentials
        elif active is None and index_identity(settings)[:2] == (body.provider, base_url):
            token = (
                seal_integration_secret(settings.embedding_api_key)
                if settings.embedding_api_key
                else None
            )
    if body.provider == "openai" and not token:
        raise AppError(422, "reindex_key_required", "Enter the target embedding provider key")
    db.execute(delete(ReindexVector).where(ReindexVector.organization_id == organization_id))
    if job is None:
        job = EmbeddingReindex(organization_id=organization_id)
        db.add(job)
    job.provider = body.provider
    job.requested_by = actor_id
    job.config = {"base_url": base_url, "model": model, "dimensions": body.dimensions}
    job.base = _revision(active)
    job.encrypted_credentials = token
    job.status = "building"
    job.error_code = None
    job.updated_at = datetime.now(UTC)
    record_event(
        db, organization_id, "embedding_reindex_started", {"model": model}, actor_id=actor_id
    )
    db.commit()
    return job


def progress(db: Session, organization_id: uuid.UUID) -> dict[str, object] | None:
    job = db.get(EmbeddingReindex, organization_id)
    if job is None:
        return None
    total = db.scalar(select(func.count(Chunk.id)).where(Chunk.organization_id == organization_id))
    staged = db.scalar(
        select(func.count(ReindexVector.chunk_id)).where(
            ReindexVector.organization_id == organization_id
        )
    )
    return {
        "status": job.status,
        "model": job.config["model"],
        "dimensions": job.config["dimensions"],
        "total_chunks": total or 0,
        "staged_chunks": total if job.status == "completed" else staged or 0,
        "error_code": job.error_code,
    }


def _finish(db: Session, job: EmbeddingReindex, status: str, error: str | None = None) -> None:
    db.execute(delete(ReindexVector).where(ReindexVector.organization_id == job.organization_id))
    job.status, job.error_code = status, error
    job.encrypted_credentials = None
    job.updated_at = datetime.now(UTC)
    record_event(db, job.organization_id, "embedding_reindex_" + status, {"reason": error})
    db.commit()


def cancel(db: Session, organization_id: uuid.UUID) -> None:
    job = db.get(EmbeddingReindex, organization_id, with_for_update=True)
    if job is None or job.status != "building":
        raise AppError(409, "reindex_not_running", "There is no active index build")
    _finish(db, job, "cancelled")


def _missing(organization_id: uuid.UUID) -> Any:
    return (
        select(Chunk.id, Chunk.content)
        .outerjoin(
            ReindexVector,
            and_(
                ReindexVector.organization_id == organization_id,
                ReindexVector.chunk_id == Chunk.id,
            ),
        )
        .where(Chunk.organization_id == organization_id, ReindexVector.chunk_id.is_(None))
    )


def _client(job: EmbeddingReindex) -> OpenAICompatibleEmbeddingClient:
    return OpenAICompatibleEmbeddingClient(
        get_settings().model_copy(
            update={
                "embedding_provider": job.provider,
                "embedding_base_url": job.config["base_url"],
                "embedding_model": job.config["model"],
                "embedding_dimensions": job.config["dimensions"],
                "embedding_api_key": open_integration_secret(job.encrypted_credentials)
                if job.encrypted_credentials
                else "",
            }
        )
    )


def _embed(job: EmbeddingReindex, texts: list[str]) -> list[list[float]]:
    vectors = _client(job).embed(texts)
    if len(vectors) != len(texts) or any(
        len(vector) != job.config["dimensions"]
        or not all(math.isfinite(v) for v in vector)
        or not any(vector)
        for vector in vectors
    ):
        raise AppError(
            502, "embedding_dimension_mismatch", "The candidate returned invalid vectors"
        )
    return vectors


def run_batch(db: Session) -> bool:
    job = db.scalar(
        select(EmbeddingReindex)
        .where(EmbeddingReindex.status == "building")
        .order_by(EmbeddingReindex.updated_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return False
    organization_id = job.organization_id
    missing = _missing(organization_id).order_by(Chunk.id)
    batch = db.execute(missing.limit(_BATCH_SIZE)).all()
    try:
        if batch:
            vectors = _embed(job, [row.content for row in batch])
            lock_embedding_index(db, organization_id)
            ids = set(
                db.scalars(
                    select(Chunk.id).where(
                        Chunk.organization_id == organization_id,
                        Chunk.id.in_([row.id for row in batch]),
                    )
                )
            )
            db.add_all(
                ReindexVector(organization_id=organization_id, chunk_id=row.id, vector=vector)
                for row, vector in zip(batch, vectors, strict=True)
                if row.id in ids
            )
            job.updated_at = datetime.now(UTC)
            db.commit()
        else:
            if (
                db.scalar(
                    select(ReindexVector.chunk_id)
                    .where(ReindexVector.organization_id == organization_id)
                    .limit(1)
                )
                is None
            ):
                _embed(job, ["ATLAS embedding verification"])
            _promote(db, job, missing)
    except AppError as exc:
        _finish(db, job, "failed", exc.code)
    return True


def _promote(db: Session, job: EmbeddingReindex, missing: Any) -> None:
    organization_id = job.organization_id
    lock_embedding_index(db, organization_id)
    active = _active(db, organization_id, lock=True)
    if job.base != _revision(active):
        _finish(db, job, "failed", "embedding_configuration_changed")
        return
    if db.execute(missing.limit(1)).first() is not None:
        db.commit()
        return
    dimensions = job.config["dimensions"]
    vector = cast(cast(ReindexVector.vector, Text), Vector(dimensions))
    db.execute(
        update(Chunk)
        .where(
            Chunk.organization_id == organization_id,
            ReindexVector.organization_id == organization_id,
            ReindexVector.chunk_id == Chunk.id,
        )
        .values(
            embedding=vector if dimensions == 1536 else None,
            embedding_768=vector if dimensions == 768 else None,
            embedding_model=job.config["model"],
        )
        .execution_options(synchronize_session=False)
    )
    if active is None:
        active = IntegrationConfig(
            organization_id=organization_id,
            integration_type=IntegrationType.embedding,
            credential_version=0,
        )
        db.add(active)
    active.provider = job.provider
    active.config = dict(job.config)
    active.encrypted_credentials = job.encrypted_credentials
    active.credential_version += 1
    active.status = IntegrationStatus.configured
    active.verified_at = datetime.now(UTC)
    active.verification_detail = "A replacement index was built and activated."
    _finish(db, job, "completed")

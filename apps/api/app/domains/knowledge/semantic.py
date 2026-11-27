"""In-process semantic vectors for one visitor organization.

The basis is latent semantic analysis over that organization's own chunks.
A query is projected into the same space. Another organization's text is not
loaded, and no embedding request leaves the process.
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.knowledge.models import Chunk
from app.domains.knowledge.vectors import store_chunk_embedding
from app.integrations.doubles import hash_embedding

VISITOR_SEMANTIC_MODEL = "visitor-semantic"


class VisitorSemanticEmbedder:
    def __init__(self, db: Session, organization_id: uuid.UUID) -> None:
        self._db = db
        self._organization_id = organization_id
        base = get_settings()
        self._settings = base.model_copy(
            update={
                "embedding_provider": "double",
                "embedding_model": VISITOR_SEMANTIC_MODEL,
                "embedding_dimensions": base.embedding_dimensions,
                "public_demo": False,
            }
        )

    @property
    def settings(self) -> Settings:
        return self._settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        rows = list(
            self._db.scalars(
                select(Chunk)
                .where(Chunk.organization_id == self._organization_id)
                .order_by(Chunk.document_id, Chunk.chunk_index, Chunk.id)
            ).all()
        )
        width = self._settings.embedding_dimensions
        basis = [row.content for row in rows] or list(texts)
        projected = semantic_vectors(basis, basis, width)
        if rows and len(projected) == len(rows):
            for row, vector in zip(rows, projected, strict=True):
                store_chunk_embedding(row, vector, self._settings)
            self._db.flush()
        return semantic_vectors(basis, texts, width)


def semantic_vectors(basis: list[str], texts: list[str], width: int) -> list[list[float]]:
    """Project texts into a space fitted only on the supplied basis."""

    if not texts:
        return []
    if len(basis) < 3:
        return [hash_embedding(text, width) for text in texts]
    try:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        return [hash_embedding(text, width) for text in texts]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(basis)
    components = min(48, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if components < 2:
        return [hash_embedding(text, width) for text in texts]
    model = TruncatedSVD(n_components=components, random_state=0, algorithm="arpack")
    try:
        model.fit(matrix)
    except ValueError:
        model = TruncatedSVD(n_components=components, random_state=0)
        model.fit(matrix)
    projected = model.transform(vectorizer.transform(texts))
    vectors: list[list[float]] = []
    for row in projected:
        padded = [0.0] * width
        for index, value in enumerate(row.tolist()):
            if index >= width:
                break
            padded[index] = float(value)
        norm = math.sqrt(sum(value * value for value in padded)) or 1.0
        vectors.append([value / norm for value in padded])
    return vectors

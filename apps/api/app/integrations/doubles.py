"""Deterministic chat and embedding stand-ins.

These are not a live model provider. Production refuses to select them.
"""

import hashlib
import math
import re
from collections.abc import Iterator


def hash_embedding(text: str, dimensions: int = 1536) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]+", text.lower()) or ["empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        for offset in range(0, 16, 2):
            index = int.from_bytes(digest[offset : offset + 2], "big") % dimensions
            vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class DeterministicEmbeddingClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embedding(text) for text in texts]


class DeterministicChatClient:
    def ensure_configured(self) -> None:
        return None

    def complete(self, system: str, user: str) -> str:
        if "json" in system.lower():
            return (
                '{"category":"warehousing","contact_name":"Mina Patel","company_name":"Harbor",'
                '"summary":"Rates for bonded storage","lead_title":"Bonded storage inquiry",'
                '"draft_response":"We can discuss bonded storage."}'
            )
        return "Grounded answer from the supplied company records."

    def stream(self, system: str, user: str) -> Iterator[str]:
        yield self.complete(system, user)

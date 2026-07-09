from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable


EMBEDDING_DIMENSION = 1536


def tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[_/,\-]", " ", str(text or "").lower())
    normalized = re.sub(r"[^\w\s가-힣]+", " ", normalized)
    return [token for token in normalized.split() if len(token) >= 2]


def hash_embedding(text: str, *, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + min(len(token), 16) / 16.0
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"

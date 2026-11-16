"""Pure retrieval functions: vectors in, ordered results out.

No HTTP, no SQLite, no model loading. Everything here is deterministic for a
given input, which makes it trivial to unit-test.
"""
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True, slots=True)
class ScoredId:
    post_id: int
    score: float


def cosine_similarity(query: ArrayLike, matrix: ArrayLike) -> NDArray[np.float64]:
    """Cosine similarity between ``query`` (d,) and every row of ``matrix`` (n, d).

    A zero-norm query or row scores 0.0 (never NaN/inf). Scores are clipped to [-1, 1].
    """
    q = np.asarray(query, dtype=np.float64).ravel()
    m = np.asarray(matrix, dtype=np.float64)
    if m.size == 0:
        return np.zeros(0, dtype=np.float64)
    m = np.atleast_2d(m)
    if m.shape[1] != q.shape[0]:
        raise ValueError(f"dimension mismatch: query has {q.shape[0]}, matrix rows have {m.shape[1]}")

    denominators = np.linalg.norm(m, axis=1) * np.linalg.norm(q)
    scores = np.zeros(m.shape[0], dtype=np.float64)
    np.divide(m @ q, denominators, out=scores, where=denominators > 0)
    return np.clip(scores, -1.0, 1.0)


def top_k(scores: ArrayLike, post_ids: ArrayLike, k: int) -> list[ScoredId]:
    """Best ``k`` entries by score descending; equal scores ordered by ascending post_id."""
    s = np.asarray(scores, dtype=np.float64).ravel()
    ids = np.asarray(post_ids, dtype=np.int64).ravel()
    if s.shape != ids.shape:
        raise ValueError("scores and post_ids must have the same length")
    k = max(0, min(int(k), s.shape[0]))
    order = np.lexsort((ids, -s))[:k]  # last key is primary: -score, then post_id
    return [ScoredId(post_id=int(ids[i]), score=float(s[i])) for i in order]


def rank(query_vector: ArrayLike, matrix: ArrayLike, post_ids: ArrayLike, k: int) -> list[ScoredId]:
    """Score every row against the query and return the ordered top-k."""
    return top_k(cosine_similarity(query_vector, matrix), post_ids, k)

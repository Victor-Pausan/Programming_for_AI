"""Search use case: builds the in-memory index and answers queries.

Coordinates the encoder adapter, the post repository and the pure retrieval
functions. No HTTP and no SQL here.
"""
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.db.repository import PostReader
from app.domain.models import Post
from app.search.encoder import TextEncoder
from app.search.retrieval import rank

MIN_LIMIT = 1
MAX_LIMIT = 20


class InvalidSearchError(ValueError):
    """The query or limit breaks the search rules."""


@dataclass(frozen=True, slots=True)
class SearchHit:
    post: Post
    score: float


@dataclass(frozen=True)
class SearchIndex:
    """Posts and their embeddings, row i of ``vectors`` belongs to ``posts[i]``."""

    posts: tuple[Post, ...]
    vectors: NDArray[np.float32]

    def __post_init__(self) -> None:
        if len(self.posts) != self.vectors.shape[0]:
            raise ValueError("posts and vectors must have the same length")

    @property
    def post_ids(self) -> NDArray[np.int64]:
        return np.array([p.id for p in self.posts], dtype=np.int64)


def build_index(repository: PostReader, encoder: TextEncoder) -> SearchIndex:
    """Read every post and encode its content (done once at application startup)."""
    posts = tuple(repository.list_posts())
    vectors = encoder.encode([p.content for p in posts])
    return SearchIndex(posts=posts, vectors=np.asarray(vectors, dtype=np.float32))


def search_posts(query: str, limit: int, index: SearchIndex, encoder: TextEncoder) -> list[SearchHit]:
    """Return up to ``limit`` posts most similar to ``query``.

    Ordered by descending score, ties broken by ascending post id.

    Raises:
        InvalidSearchError: blank query or limit outside [MIN_LIMIT, MAX_LIMIT].
    """
    text = query.strip()
    if not text:
        raise InvalidSearchError("q must not be empty")
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        raise InvalidSearchError(f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}")
    if not index.posts:
        return []

    query_vector = encoder.encode([text])[0]
    by_id = {p.id: p for p in index.posts}
    return [
        SearchHit(post=by_id[hit.post_id], score=hit.score)
        for hit in rank(query_vector, index.vectors, index.post_ids, limit)
    ]

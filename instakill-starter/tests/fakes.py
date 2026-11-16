"""Test doubles: deterministic encoder and in-memory post reader (no model, no SQLite)."""
import re

import numpy as np

from app.domain.models import Post

VOCAB = ["cheap", "dinner", "restaurant", "run", "river", "python", "numpy", "music", "jazz", "spam"]


class BagOfWordsEncoder:
    """Counts vocabulary words; texts with no known word map to the zero vector."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        rows = []
        for text in texts:
            tokens = re.findall(r"[a-z]+", text.lower())
            rows.append([tokens.count(word) for word in VOCAB])
        return np.asarray(rows, dtype=np.float32).reshape(len(texts), len(VOCAB))


class InMemoryPosts:
    def __init__(self, posts: list[Post]) -> None:
        self._posts = posts

    def list_posts(self) -> list[Post]:
        return list(self._posts)


SAMPLE_POSTS = [
    Post(id=1, user_id=1, content="cheap dinner at the new restaurant"),
    Post(id=2, user_id=2, content="evening run by the river"),
    Post(id=3, user_id=3, content="numpy makes python fast"),
    Post(id=4, user_id=4, content="cheap dinner at the new restaurant"),  # exact tie with post 1
    Post(id=5, user_id=5, content="late jazz music"),
    Post(id=6, user_id=1, content="hello world"),  # zero vector under the fake encoder
]

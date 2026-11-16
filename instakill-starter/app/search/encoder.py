"""Text-encoder adapter: the only module that knows about the embedding model."""
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class TextEncoder(Protocol):
    def encode(self, texts: list[str]) -> NDArray[np.float32]:
        """Return one embedding row per input text, shape (len(texts), dim)."""
        ...


class SentenceTransformerEncoder:
    """Pretrained Sentence-Transformers encoder on CPU, loaded lazily on first use."""

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, deferred

            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def encode(self, texts: list[str]) -> NDArray[np.float32]:
        model = self._load()
        if not texts:
            return np.zeros((0, model.get_sentence_embedding_dimension()), dtype=np.float32)
        vectors = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)

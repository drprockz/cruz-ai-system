"""
EmbeddingService — sentence-transformers wrapper for CRUZ semantic memory.

Uses all-MiniLM-L6-v2 (384 dimensions, ~22MB, fast CPU inference).
Model is loaded lazily on first encode() call — no startup cost.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sentence_transformers import SentenceTransformer  # noqa: E402

logger = logging.getLogger("cruz.services.embedding")

_MODEL_NAME = "all-MiniLM-L6-v2"

# Module-level singleton
_instance: Optional["EmbeddingService"] = None


def get_embedding_service() -> "EmbeddingService":
    """Return the module-level EmbeddingService singleton."""
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance


class EmbeddingService:
    """Lazy-loading wrapper around sentence-transformers SentenceTransformer."""

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None  # loaded on first encode()

    def _get_model(self):
        if self._model is None:
            logger.info("Loading embedding model '%s'…", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            logger.info("Embedding model loaded.")
        return self._model

    def encode(self, text: str) -> List[float]:
        """
        Encode text into a 384-dimensional float vector.

        Args:
            text: The string to embed.

        Returns:
            List of 384 floats (cosine-normalised by default).
        """
        model = self._get_model()
        embedding = model.encode(text)
        return embedding.tolist()

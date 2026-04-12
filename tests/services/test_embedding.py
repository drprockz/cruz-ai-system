"""
Tests for EmbeddingService — sentence-transformers wrapper.

EmbeddingService wraps all-MiniLM-L6-v2 and exposes:
  - encode(text) → List[float] of length 384
  - Model is loaded lazily (not at import time)
  - Module singleton via get_embedding_service()

The actual SentenceTransformer model is mocked — tests run fast
without downloading the model.

RED phase — must fail before production code exists.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.embedding import EmbeddingService, get_embedding_service


def _make_mock_model(vector_size: int = 384):
    """Return a mock SentenceTransformer that returns a fixed-size numpy array."""
    import numpy as np

    model = MagicMock()
    model.encode = MagicMock(return_value=np.ones(vector_size, dtype="float32"))
    return model


class TestEmbeddingServiceInterface:
    def test_embedding_service_can_be_instantiated(self):
        assert EmbeddingService() is not None

    def test_has_encode_method(self):
        assert hasattr(EmbeddingService(), "encode")

    def test_get_embedding_service_returns_instance(self):
        svc = get_embedding_service()
        assert isinstance(svc, EmbeddingService)

    def test_get_embedding_service_is_singleton(self):
        assert get_embedding_service() is get_embedding_service()


class TestEmbeddingServiceEncode:
    def test_encode_returns_list(self):
        svc = EmbeddingService()
        mock_model = _make_mock_model(384)

        with patch.object(svc, "_get_model", return_value=mock_model):
            result = svc.encode("Hello world")

        assert isinstance(result, list)

    def test_encode_returns_floats(self):
        svc = EmbeddingService()
        mock_model = _make_mock_model(384)

        with patch.object(svc, "_get_model", return_value=mock_model):
            result = svc.encode("some text")

        assert all(isinstance(v, float) for v in result)

    def test_encode_returns_384_dimensions(self):
        svc = EmbeddingService()
        mock_model = _make_mock_model(384)

        with patch.object(svc, "_get_model", return_value=mock_model):
            result = svc.encode("testing dimensions")

        assert len(result) == 384

    def test_encode_passes_text_to_model(self):
        svc = EmbeddingService()
        mock_model = _make_mock_model()

        with patch.object(svc, "_get_model", return_value=mock_model):
            svc.encode("unique-test-text-string")

        mock_model.encode.assert_called_once_with("unique-test-text-string")

    def test_model_loaded_lazily_not_at_init(self):
        """SentenceTransformer must NOT be imported/loaded at instantiation."""
        with patch("services.embedding.SentenceTransformer") as MockST:
            EmbeddingService()
            MockST.assert_not_called()

    def test_model_loaded_on_first_encode(self):
        svc = EmbeddingService()

        with patch("services.embedding.SentenceTransformer", return_value=_make_mock_model()) as MockST:
            svc.encode("trigger load")

        MockST.assert_called_once()

    def test_model_not_reloaded_on_second_encode(self):
        svc = EmbeddingService()

        with patch("services.embedding.SentenceTransformer", return_value=_make_mock_model()) as MockST:
            svc.encode("first call")
            svc.encode("second call")

        MockST.assert_called_once()  # loaded once, reused

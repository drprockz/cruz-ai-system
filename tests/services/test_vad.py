"""
Tests for SileroVAD — voice activity detection wrapper.

Silero VAD is a ~1.8MB ONNX model that returns a 0.0-1.0 speech
probability per ~30ms frame at 16kHz. We wrap it in a thin class so
the voice daemon can ask "is this frame speech?" without knowing the
model internals.

The `silero_vad` pip package is optional — tests patch the module
attribute so CI doesn't need the 1.8MB download.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSileroVADInterface:
    def test_can_be_imported(self):
        from services.vad import SileroVAD  # noqa: F401

    def test_raises_when_package_not_installed(self):
        """Graceful error when silero-vad isn't installed."""
        from services.vad import SileroVAD
        with patch("services.vad.silero_vad", None):
            with pytest.raises(RuntimeError, match="silero-vad"):
                SileroVAD()

    def test_init_loads_model(self):
        from services.vad import SileroVAD
        fake_model = MagicMock()
        fake_pkg = MagicMock()
        fake_pkg.load_silero_vad = MagicMock(return_value=fake_model)
        with patch("services.vad.silero_vad", fake_pkg):
            vad = SileroVAD()
        fake_pkg.load_silero_vad.assert_called_once()
        assert vad._model is fake_model


class TestSileroVADIsSpeech:
    def test_returns_true_when_score_above_threshold(self):
        from services.vad import SileroVAD
        fake_model = MagicMock()
        fake_model.return_value = MagicMock()
        fake_model.return_value.item = MagicMock(return_value=0.87)
        fake_pkg = MagicMock()
        fake_pkg.load_silero_vad = MagicMock(return_value=fake_model)
        with patch("services.vad.silero_vad", fake_pkg):
            vad = SileroVAD(threshold=0.5)
            import numpy as np
            assert vad.is_speech(np.zeros(512, dtype=np.int16)) is True

    def test_returns_false_when_below_threshold(self):
        from services.vad import SileroVAD
        fake_model = MagicMock()
        fake_model.return_value = MagicMock()
        fake_model.return_value.item = MagicMock(return_value=0.12)
        fake_pkg = MagicMock()
        fake_pkg.load_silero_vad = MagicMock(return_value=fake_model)
        with patch("services.vad.silero_vad", fake_pkg):
            vad = SileroVAD(threshold=0.5)
            import numpy as np
            assert vad.is_speech(np.zeros(512, dtype=np.int16)) is False

    def test_custom_threshold_respected(self):
        from services.vad import SileroVAD
        fake_model = MagicMock()
        fake_model.return_value = MagicMock()
        fake_model.return_value.item = MagicMock(return_value=0.30)
        fake_pkg = MagicMock()
        fake_pkg.load_silero_vad = MagicMock(return_value=fake_model)
        with patch("services.vad.silero_vad", fake_pkg):
            vad = SileroVAD(threshold=0.25)  # lower than 0.30 → match
            import numpy as np
            assert vad.is_speech(np.zeros(512, dtype=np.int16)) is True

    def test_expected_frame_length_is_512(self):
        """Silero VAD at 16kHz sample rate expects 512-sample frames."""
        from services.vad import SileroVAD
        assert SileroVAD.FRAME_LENGTH == 512
        assert SileroVAD.SAMPLE_RATE == 16000

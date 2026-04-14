"""
SileroVAD — voice activity detector.

Silero VAD is a tiny (~1.8 MB) ONNX model that reports a speech
probability per ~30 ms audio frame at 16 kHz. We wrap it with a simple
`is_speech(frame)` method so the voice daemon can cleanly ask "did
the user start/stop speaking in this frame?"

Usage:
    from services.vad import SileroVAD

    vad = SileroVAD(threshold=0.5)
    # Feed 512-sample int16 frames @ 16 kHz (30 ms):
    if vad.is_speech(frame):
        ...

The `silero-vad` pip package is optional — the module loads whether
it's installed or not, but constructing `SileroVAD()` raises a clear
error if the package is missing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("cruz.services.vad")

try:  # lazy — test suite patches services.vad.silero_vad
    import silero_vad  # type: ignore
except ImportError:  # pragma: no cover — only needed at runtime
    silero_vad = None  # type: ignore


class SileroVAD:
    """
    Thin wrapper around Silero VAD.

    Contract:
        FRAME_LENGTH  — expected int16 samples per call (512 at 16kHz)
        SAMPLE_RATE   — 16 kHz, per Silero VAD's training set
        is_speech(x)  — returns True if speech probability >= threshold

    The VAD is stateful — it remembers recent audio context internally.
    Create one instance per capture session; call `reset()` between
    unrelated utterances if needed.
    """

    FRAME_LENGTH = 512
    SAMPLE_RATE = 16000

    def __init__(self, threshold: float = 0.5) -> None:
        if silero_vad is None:
            raise RuntimeError(
                "silero-vad package not installed. "
                "Run `pip install silero-vad` to enable voice "
                "activity detection."
            )
        self._model: Any = silero_vad.load_silero_vad()
        self._threshold = float(threshold)

    def is_speech(self, frame: Any) -> bool:
        """
        Return True iff this frame's Silero speech probability >= threshold.

        `frame` should be a numpy int16 array of length FRAME_LENGTH.
        The model internally converts to float32 in the -1..1 range and
        runs ONNX inference (~1 ms on M-series CPU).
        """
        try:
            import torch
        except ImportError:  # pragma: no cover
            raise RuntimeError(
                "torch is required by silero-vad. Install with "
                "`pip install torch silero-vad`."
            )

        # Convert int16 → float32 in [-1, 1]
        if hasattr(frame, "astype"):
            tensor = torch.from_numpy(
                frame.astype("float32") / 32768.0
            ).squeeze()
        else:
            tensor = torch.tensor(
                [x / 32768.0 for x in frame], dtype=torch.float32,
            )

        prob = self._model(tensor, self.SAMPLE_RATE).item()
        return prob >= self._threshold

    def reset(self) -> None:
        """Clear internal VAD state between unrelated captures."""
        if hasattr(self._model, "reset_states"):
            try:
                self._model.reset_states()
            except Exception:
                pass

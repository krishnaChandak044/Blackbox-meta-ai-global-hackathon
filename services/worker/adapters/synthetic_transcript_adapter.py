"""
services/worker/adapters/synthetic_transcript_adapter.py

DEMO ONLY — generates a deterministic placeholder transcript when no real
transcription service is available.

⚠️  SAFETY CONTRACT:
    - is_synthetic=True is always set on the returned TranscriptResult.
    - The worker (transcription.py) MUST surface this flag to the UI and must
      NOT allow claims derived from a synthetic transcript to be treated as
      real witness evidence.
    - This adapter should NEVER be used automatically in a production pipeline.
      It must only be enabled when ENABLE_SYNTHETIC_TRANSCRIPT=true is set.
"""

from __future__ import annotations

import hashlib
import os
import random

from services.worker.adapters.muse_voice_adapter import TranscriptResult

_PLACEHOLDER_SEGMENTS = [
    "Transcription unavailable — no transcription service is configured.",
    "To transcribe this clip, set MUSE_VOICE_API_KEY and MUSE_VOICE_API_URL.",
    "This placeholder text is NOT a real witness statement.",
]


class SyntheticTranscriptAdapter:
    """
    Generates a deterministic PLACEHOLDER transcript for demo/dev purposes.

    ONLY used when ENABLE_SYNTHETIC_TRANSCRIPT=true is explicitly set.
    Returns is_synthetic=True so all downstream consumers know this is not
    real evidence.
    """

    TRANSCRIPTION_MODEL = "synthetic-placeholder-v0"

    def transcribe(
        self,
        audio_path: str,
        *,
        media_id: str = "",
        duration_seconds: float | None = None,
        language: str = "en",
    ) -> TranscriptResult:
        dur = duration_seconds or 10.0
        # Produce a clearly-labelled placeholder — not fake witness statements
        raw_text = " ".join(_PLACEHOLDER_SEGMENTS)
        seg_len = dur / len(_PLACEHOLDER_SEGMENTS)
        segments: list[dict] = [
            {
                "speaker": "system",
                "start": round(i * seg_len, 2),
                "end": round((i + 1) * seg_len, 2),
                "text": txt,
            }
            for i, txt in enumerate(_PLACEHOLDER_SEGMENTS)
        ]
        return TranscriptResult(
            raw_text=raw_text,
            language=language,
            diarised_segments=segments,
            duration_seconds=dur,
            transcription_model=self.TRANSCRIPTION_MODEL,
            is_synthetic=True,   # ← always True — non-negotiable
        )

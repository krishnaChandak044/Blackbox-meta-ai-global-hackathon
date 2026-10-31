"""
services/worker/adapters/muse_voice_adapter.py

Calls Meta Muse Voice Transcribe API.

Critical notes:
- Raises AdapterUnavailable (NOT a generic exception) when env vars are absent.
  The worker must catch AdapterUnavailable specifically — never fall back
  silently to a synthetic adapter that could invent witness statements.
- Does NOT send raw video bytes. Audio must be extracted first (see extract_audio).
- Validates the API response shape before returning.
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import tempfile
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


class AdapterUnavailable(RuntimeError):
    """Raised when a transcription adapter cannot be used (missing config, no tool, etc.)."""


@dataclass(frozen=True, slots=True)
class TranscriptResult:
    raw_text: str
    language: str
    diarised_segments: list[dict]
    duration_seconds: float | None
    transcription_model: str
    # is_synthetic=True means the text was machine-generated for demo purposes,
    # NOT a real transcription of audio evidence. Any claims derived from it
    # MUST carry this flag so downstream consumers can refuse to treat them as
    # real witness statements.
    is_synthetic: bool = False


def extract_audio(video_path: str, dest_path: str) -> None:
    """
    Extract audio track from a video file to a WAV file using ffmpeg.

    Raises AdapterUnavailable if ffmpeg is not on PATH.
    Raises RuntimeError if extraction fails.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vn",                  # no video
                "-ac", "1",             # mono
                "-ar", "16000",         # 16 kHz — standard for speech models
                "-acodec", "pcm_s16le", # WAV PCM
                dest_path,
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise RuntimeError(f"ffmpeg failed (rc={result.returncode}): {stderr[:500]}")
    except FileNotFoundError as exc:
        raise AdapterUnavailable("ffmpeg not found on PATH — cannot extract audio from video") from exc


class MuseVoiceAdapter:
    """
    Calls Meta Muse Voice Transcribe API.

    Raises AdapterUnavailable when:
    - MUSE_VOICE_API_KEY is not set
    - MUSE_VOICE_API_URL is not set
    - ffmpeg is not available (needed to extract audio from video)
    - The API returns a non-2xx response

    NEVER falls back silently. The caller (transcription.py) decides what to do
    when this adapter is unavailable.
    """

    TRANSCRIPTION_MODEL = "muse-voice-v1"

    def __init__(self, api_url: str | None = None, api_key: str | None = None) -> None:
        self.api_url = (api_url or os.getenv("MUSE_VOICE_API_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("MUSE_VOICE_API_KEY", "")

    @staticmethod
    def _endpoint(base_url: str) -> str:
        """Resolve a configured service URL without silently duplicating routes.

        Configure either the transcription endpoint itself or a base URL ending
        in `/v1/muse/voice`; in the latter case `/transcribe` is appended.
        """
        base = base_url.rstrip("/")
        return base if base.endswith("/transcribe") else f"{base}/transcribe"

    def _ensure_available(self) -> None:
        if not self.api_key:
            raise AdapterUnavailable("MUSE_VOICE_API_KEY is not set")
        if not self.api_url:
            raise AdapterUnavailable("MUSE_VOICE_API_URL is not set")

    def transcribe(self, video_or_audio_path: str) -> TranscriptResult:
        """
        Transcribe a video or audio file.

        If the file is a video (non-WAV/MP3/FLAC/OGG), audio is first extracted
        via ffmpeg to a temporary WAV file. Only the audio is sent to the API.
        """
        self._ensure_available()

        src = pathlib.Path(video_or_audio_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {video_or_audio_path}")

        # Determine if we need audio extraction
        audio_suffixes = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
        needs_extraction = src.suffix.lower() not in audio_suffixes

        tmp_wav = None
        try:
            if needs_extraction:
                tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_wav.close()
                logger.info("muse_voice.extracting_audio", extra={"src": str(src), "dst": tmp_wav.name})
                extract_audio(str(src), tmp_wav.name)
                audio_path = tmp_wav.name
            else:
                audio_path = str(src)

            return self._call_api(audio_path)

        finally:
            if tmp_wav is not None:
                pathlib.Path(tmp_wav.name).unlink(missing_ok=True)

    def _call_api(self, audio_path: str) -> TranscriptResult:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with open(audio_path, "rb") as fh:
                suffix = pathlib.Path(audio_path).suffix.lower()
                content_type = "audio/wav" if suffix == ".wav" else {
                    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg",
                    ".m4a": "audio/mp4", ".aac": "audio/aac", ".opus": "audio/opus",
                }.get(suffix)
                if content_type is None:
                    raise AdapterUnavailable(f"Unsupported audio format: {suffix or 'unknown'}")
                files = {"file": (pathlib.Path(audio_path).name, fh, content_type)}
                resp = httpx.post(
                    self._endpoint(self.api_url),
                    files=files,
                    headers=headers,
                    timeout=300.0,   # large files can take time
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise AdapterUnavailable(
                f"Muse Voice API HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterUnavailable(f"Muse Voice API network error: {exc}") from exc

        # Validate response shape
        if not isinstance(data, dict):
            raise AdapterUnavailable(f"Unexpected API response type: {type(data)}")

        segments: list[dict] = data.get("segments") or data.get("diarised") or []
        if not isinstance(segments, list) or any(not isinstance(s, dict) for s in segments):
            raise AdapterUnavailable("Muse Voice response contains malformed segments")
        raw_text: str = (
            data.get("text")
            or " ".join(s.get("text", "") for s in segments)
        ).strip()

        if not raw_text:
            raise AdapterUnavailable("API returned empty transcript text")

        return TranscriptResult(
            raw_text=raw_text,
            language=data.get("language", "en"),
            diarised_segments=self._normalise_segments(segments),
            duration_seconds=data.get("duration_seconds"),
            transcription_model=self.TRANSCRIPTION_MODEL,
            is_synthetic=False,
        )

    @staticmethod
    def _normalise_segments(raw: list[dict]) -> list[dict]:
        """
        Normalise diarisation segments to a consistent shape:
        {speaker: str, start: float, end: float, text: str}
        """
        out = []
        for s in raw:
            try:
                start = float(s.get("start", 0))
                end = float(s.get("end", 0))
            except (TypeError, ValueError) as exc:
                raise AdapterUnavailable("Muse Voice returned invalid segment timestamps") from exc
            if start < 0 or end < start:
                raise AdapterUnavailable("Muse Voice returned an invalid segment time range")
            speaker = (
                s.get("speaker")
                or s.get("speaker_label")
                or s.get("spk")
                or "unknown"
            )
            out.append({
                "speaker": str(speaker),
                "start": start,
                "end": end,
                "text": str(s.get("text", s.get("content", ""))).strip(),
            })
        return out

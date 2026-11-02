"""SAM 3.1 video tracking through the Meta Model API."""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import av
from meta_sam_parser import (
    SegmentationBoxRecord,
    parse_responses_stream,
    video_segmentation_format,
)

from engine.tracking.protocols import BoundingBox, ObjectLabel, Track, TrackPoint
from services.worker.adapters.muse_voice_adapter import AdapterUnavailable

logger = logging.getLogger(__name__)


class SamMetaApiTracker:
    """Upload one clip, request per-concept tracking, and return source-frame boxes.

    The remote file is deleted after processing. API or parse failures are not
    silently replaced with local tracking because that could misrepresent which
    model produced the evidence.
    """

    MODEL_NAME = "sam-3.1-meta-api"
    MODEL_VERSION = "sam-3.1"
    DEFAULT_BASE_URL = "https://api.meta.ai/v1"
    CONCEPTS = (("vehicle", "vehicle"), ("pedestrian", "person"), ("cyclist", "bicycle"))

    def __init__(self, api_url: str | None = None, api_key: str | None = None) -> None:
        self.api_url = (api_url or os.getenv("SAM_API_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.getenv("SAM_API_KEY") or os.getenv("MODEL_API_KEY", "")

    def _ensure_available(self) -> None:
        if not self.api_key:
            raise AdapterUnavailable("Set SAM_API_KEY to enable Meta SAM 3.1 tracking")
        if not self.api_url.startswith("https://"):
            raise AdapterUnavailable("SAM_API_URL must be the HTTPS Meta API base URL")

    def track(
        self,
        video_path: str,
        *,
        category_filter: Sequence[str] | None = None,
        min_confidence: float = 0.4,
    ) -> list[Track]:
        self._ensure_available()
        source = Path(video_path)
        if not source.is_file():
            raise FileNotFoundError(f"Video file missing: {video_path}")
        return asyncio.run(self._track_async(source, category_filter, min_confidence))

    async def _track_async(
        self,
        source: Path,
        category_filter: Sequence[str] | None,
        min_confidence: float,
    ) -> list[Track]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - installation/configuration failure
            raise AdapterUnavailable("Install the openai package to use Meta SAM 3.1") from exc

        client = AsyncOpenAI(base_url=self.api_url, api_key=self.api_key, timeout=900.0)
        remote_file_id: str | None = None
        try:
            with source.open("rb") as handle:
                uploaded = await client.files.create(file=handle, purpose="user_data")
            remote_file_id = uploaded.id
            timestamps = _source_timestamps(source)
            selected = set(category_filter) if category_filter else {"vehicle", "pedestrian"}
            concepts = [(category, phrase) for category, phrase in self.CONCEPTS if category in selected]
            grouped: dict[str, dict[int, TrackPoint]] = defaultdict(dict)

            for category, phrase in concepts:
                stream = await client.responses.create(
                    model=self.MODEL_VERSION,
                    input=[{
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": phrase},
                            {"type": "input_video", "file_id": remote_file_id},
                        ],
                    }],
                    stream=True,
                    metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
                )
                parsed = parse_responses_stream(stream, video_segmentation_format())
                result = await parsed.final_result()
                if getattr(result.outcome, "status", None) != "completed":
                    raise AdapterUnavailable(
                        f"Meta SAM 3.1 returned an incomplete {category} segmentation stream"
                    )
                for record in result.records:
                    if not isinstance(record, SegmentationBoxRecord) or record.frame is None:
                        continue
                    confidence = record.confidence
                    if confidence is None:
                        raise AdapterUnavailable("Meta SAM response omitted requested confidence values")
                    confidence = float(confidence)
                    if confidence < min_confidence:
                        continue
                    frame_index = record.frame.frame_index
                    if frame_index not in timestamps:
                        raise AdapterUnavailable(
                            f"Meta SAM frame {frame_index} does not map to the original video timeline"
                        )
                    box = BoundingBox(
                        float(record.left), float(record.top), float(record.right), float(record.bottom)
                    )
                    if box.width <= 0 or box.height <= 0:
                        continue
                    track_id = f"{category}-{record.object_id}"
                    grouped[track_id][frame_index] = TrackPoint(
                        frame_index=frame_index,
                        presentation_ts_s=timestamps[frame_index],
                        bbox=box,
                        label=ObjectLabel(category, confidence, self.MODEL_NAME),
                        detection_confidence=confidence,
                    )

            tracks = [
                Track(track_id=track_id, points=[points[i] for i in sorted(points)], is_complete=True)
                for track_id, points in grouped.items()
                if len(points) >= 3
            ]
            return sorted(tracks, key=lambda item: item.points[0].frame_index)
        except AdapterUnavailable:
            raise
        except Exception as exc:
            raise AdapterUnavailable(f"Meta SAM 3.1 request failed: {exc}") from exc
        finally:
            if remote_file_id:
                try:
                    await client.files.delete(remote_file_id)
                except Exception as exc:  # deletion failure should not mask analysis result
                    logger.warning("sam.remote_file_delete_failed", extra={"error": str(exc)[:200]})
            await client.close()


def _source_timestamps(video_path: Path) -> dict[int, float]:
    """Map decoded source frame indices to container presentation timestamps."""
    mapping: dict[int, float] = {}
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        fallback_fps = float(stream.average_rate or 30)
        for index, frame in enumerate(container.decode(stream)):
            mapping[index] = float(frame.time) if frame.time is not None else index / fallback_fps
    if not mapping:
        raise AdapterUnavailable("No video frames could be decoded for SAM tracking")
    return mapping

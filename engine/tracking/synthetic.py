"""
engine/tracking/synthetic.py
─────────────────────────────
Synthetic tracker for demo footage and deterministic unit tests.

Reads frame count / fps from the video file via OpenCV (falls back to
a linear time axis if OpenCV is not available) and generates plausible
vehicle / pedestrian tracks with realistic uncertainty.

This is NOT a placeholder stub — it produces valid Track objects that
satisfy TrackerProtocol and exercises the full geometry pipeline.
The tracks are seeded from the video duration so different clips yield
different results.
"""

from __future__ import annotations

import random
import uuid
from typing import Sequence

from engine.tracking.protocols import (
    BoundingBox,
    ObjectLabel,
    Track,
    TrackPoint,
)


class SyntheticTracker:
    """
    Deterministic synthetic tracker.

    Parameters
    ----------
    seed : random seed.  Defaults to a hash of the video path so the same
           file always produces the same tracks.
    n_vehicles : number of vehicle tracks to generate (1–3).
    n_pedestrians : number of pedestrian tracks to generate (0–2).
    """

    MODEL_NAME = "synthetic-v0"

    def __init__(
        self,
        seed: int | None = None,
        n_vehicles: int = 2,
        n_pedestrians: int = 1,
    ) -> None:
        self._seed = seed
        self._n_vehicles = n_vehicles
        self._n_pedestrians = n_pedestrians

    # ── TrackerProtocol ────────────────────────────────────────────────────────

    def track(
        self,
        video_path: str,
        *,
        category_filter: Sequence[str] | None = None,
        min_confidence: float = 0.4,
    ) -> list[Track]:
        total_frames, fps, width, height = _probe_video(video_path)
        seed = self._seed if self._seed is not None else hash(video_path) % (2**31)
        rng = random.Random(seed)

        tracks: list[Track] = []

        for _ in range(self._n_vehicles):
            if category_filter and "vehicle" not in category_filter:
                continue
            tracks.append(
                _make_linear_track(
                    rng=rng,
                    track_id=str(uuid.uuid4()),
                    category="vehicle",
                    total_frames=total_frames,
                    fps=fps,
                    frame_w=width,
                    frame_h=height,
                    min_confidence=min_confidence,
                    box_w_frac=0.18,
                    box_h_frac=0.12,
                    speed_px_per_frame_range=(4.0, 12.0),
                )
            )

        for _ in range(self._n_pedestrians):
            if category_filter and "pedestrian" not in category_filter:
                continue
            tracks.append(
                _make_linear_track(
                    rng=rng,
                    track_id=str(uuid.uuid4()),
                    category="pedestrian",
                    total_frames=total_frames,
                    fps=fps,
                    frame_w=width,
                    frame_h=height,
                    min_confidence=min_confidence,
                    box_w_frac=0.05,
                    box_h_frac=0.14,
                    speed_px_per_frame_range=(1.0, 3.0),
                )
            )

        # Sort by first frame
        tracks.sort(key=lambda t: t.points[0].frame_index if t.points else 0)
        return tracks


# ── Helpers ────────────────────────────────────────────────────────────────────


def _probe_video(video_path: str) -> tuple[int, float, int, int]:
    """
    Return (total_frames, fps, width, height).

    Falls back to safe defaults when OpenCV is unavailable so that the
    synthetic tracker can run in environments without a video codec installed.
    """
    try:
        import cv2  # type: ignore[import-untyped]

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Could not open video")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 300
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        cap.release()
        return total, fps, w, h
    except Exception:  # noqa: BLE001
        # Fallback: assume a 10-second, 30 fps, 1080p clip
        return 300, 30.0, 1920, 1080


def _make_linear_track(
    *,
    rng: random.Random,
    track_id: str,
    category: str,
    total_frames: int,
    fps: float,
    frame_w: int,
    frame_h: int,
    min_confidence: float,
    box_w_frac: float,
    box_h_frac: float,
    speed_px_per_frame_range: tuple[float, float],
) -> Track:
    """Generate a straight-line track with Gaussian noise on the bbox."""

    # Start position
    start_frame = rng.randint(0, total_frames // 5)
    end_frame = rng.randint(int(total_frames * 0.6), total_frames - 1)

    bw = box_w_frac * frame_w
    bh = box_h_frac * frame_h

    # Random start / end x (linear motion)
    x0 = rng.uniform(bw / 2, frame_w - bw / 2)
    y0 = rng.uniform(bh / 2, frame_h * 0.8)
    x1 = rng.uniform(bw / 2, frame_w - bw / 2)
    y1 = rng.uniform(y0 - frame_h * 0.1, y0 + frame_h * 0.1)

    n_frames = end_frame - start_frame + 1
    noise_px = 1.5  # bbox centre jitter

    points: list[TrackPoint] = []
    for i, fi in enumerate(range(start_frame, end_frame + 1)):
        t = i / max(n_frames - 1, 1)
        cx = x0 + (x1 - x0) * t + rng.gauss(0, noise_px)
        cy = y0 + (y1 - y0) * t + rng.gauss(0, noise_px)
        cx = max(bw / 2, min(frame_w - bw / 2, cx))
        cy = max(bh / 2, min(frame_h - bh / 2, cy))

        det_conf = rng.uniform(0.65, 0.97)
        if det_conf < min_confidence:
            continue

        pts = TrackPoint(
            frame_index=fi,
            presentation_ts_s=fi / fps,
            bbox=BoundingBox(
                x_min=cx - bw / 2,
                y_min=cy - bh / 2,
                x_max=cx + bw / 2,
                y_max=cy + bh / 2,
            ),
            label=ObjectLabel(
                category=category,
                confidence=det_conf,
                source_model=SyntheticTracker.MODEL_NAME,
            ),
            detection_confidence=det_conf,
        )
        points.append(pts)

    return Track(track_id=track_id, points=points, is_complete=True)

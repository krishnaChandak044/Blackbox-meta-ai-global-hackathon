"""Conservative fixed-camera motion tracks from actual decoded video frames.

This baseline detects moving regions, without assigning vehicle or pedestrian
classes. It is unsuitable for moving cameras and requires human review.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import av
import cv2
import numpy as np

from engine.tracking.protocols import BoundingBox, ObjectLabel, Track, TrackPoint


class MotionTracker:
    MODEL_NAME = "opencv-motion-v1"

    def track(
        self,
        video_path: str,
        *,
        category_filter: Sequence[str] | None = None,
        min_confidence: float = 0.4,
    ) -> list[Track]:
        if category_filter and "unknown" not in category_filter:
            return []
        subtractor = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=32)
        tracks: list[Track] = []
        active: dict[str, tuple[float, float, int]] = {}
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            for frame_index, frame in enumerate(container.decode(stream)):
                image = frame.to_ndarray(format="bgr24")
                height, width = image.shape[:2]
                mask = subtractor.apply(image)
                if frame_index < 5:
                    continue
                _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
                mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                candidates = []
                for contour in contours:
                    x, y, w, h = cv2.boundingRect(contour)
                    if w * h < max(150, width * height * 0.0004):
                        continue
                    if w > width * 0.8 or h > height * 0.8:
                        continue
                    candidates.append((x, y, w, h))
                candidates.sort(key=lambda box: box[2] * box[3], reverse=True)
                used: set[str] = set()
                timestamp = (
                    float(frame.time)
                    if frame.time is not None
                    else frame_index / float(stream.average_rate or 30)
                )
                for x, y, w, h in candidates[:30]:
                    cx, cy = x + w / 2, y + h / 2
                    choices = [
                        (abs(cx - px) + abs(cy - py), track_id)
                        for track_id, (px, py, previous) in active.items()
                        if track_id not in used and frame_index - previous <= 3
                    ]
                    distance, track_id = min(choices, default=(float("inf"), ""))
                    if distance > max(40, width * 0.08):
                        track_id = str(uuid.uuid4())
                        tracks.append(Track(track_id=track_id))
                    used.add(track_id)
                    active[track_id] = (cx, cy, frame_index)
                    point = TrackPoint(
                        frame_index=frame_index,
                        presentation_ts_s=timestamp,
                        bbox=BoundingBox(float(x), float(y), float(x + w), float(y + h)),
                        label=ObjectLabel("unknown", 0.5, self.MODEL_NAME),
                        detection_confidence=0.5,
                    )
                    next(track for track in tracks if track.track_id == track_id).points.append(
                        point
                    )
                active = {
                    key: value for key, value in active.items() if frame_index - value[2] <= 3
                }
        return [track for track in tracks if len(track.points) >= 3]

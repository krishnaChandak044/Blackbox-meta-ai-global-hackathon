"""
engine/tracking/protocols.py
─────────────────────────────
Structural typing protocols for object trackers.

Any class that satisfies TrackerProtocol can be dropped in as the tracking
backend — SAM 3.1, ByteTrack, DeepSORT, or the synthetic demo tracker.
No inheritance required; duck-typing via Protocol is sufficient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

# ── Detection / Track primitives ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """
    Axis-aligned bounding box in pixel coordinates.

    All values are floats because SAM / neural detectors produce sub-pixel
    estimates.
    """

    x_min: float  # left edge
    y_min: float  # top edge
    x_max: float  # right edge
    y_max: float  # bottom edge

    @property
    def cx(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def cy(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def ground_contact_px(self) -> tuple[float, float]:
        """
        Approximate ground-contact point as the bottom-centre of the bbox.
        This is the canonical pixel fed into the homography to get the
        real-world position of the object on the ground plane.
        """
        return (self.cx, self.y_max)


@dataclass(frozen=True, slots=True)
class ObjectLabel:
    """Semantic class with confidence."""

    category: str  # "vehicle" | "pedestrian" | "cyclist" | "unknown"
    confidence: float  # [0, 1]
    source_model: str  # e.g. "sam-3.1-hiera-large" | "synthetic-v0"


@dataclass(slots=True)
class TrackPoint:
    """
    A single detection associated with a track at a specific frame.

    Attributes
    ----------
    frame_index : zero-based frame number within the source clip.
    presentation_ts_s : presentation timestamp in seconds (from container).
        This is the *authoritative* time axis; frame_index is for indexing only.
    bbox : pixel bounding box.
    label : semantic classification.
    detection_confidence : detector score for this specific detection (not
        the track-level confidence).
    is_interpolated : True if this point was filled in by interpolation rather
        than direct detection.
    is_human_corrected : True if a human has manually moved / confirmed this
        box (audit trail flag).
    """

    frame_index: int
    presentation_ts_s: float
    bbox: BoundingBox
    label: ObjectLabel
    detection_confidence: float
    is_interpolated: bool = False
    is_human_corrected: bool = False


@dataclass(slots=True)
class Track:
    """
    A complete temporal trajectory for one object across frames.

    Attributes
    ----------
    track_id : stable identifier within a single media file run.
    points : ordered list of TrackPoints (must be sorted by frame_index).
    is_complete : True when the tracker has decided the track has ended
        (left frame / occlusion resolved / etc.).
    """

    track_id: str
    points: list[TrackPoint] = field(default_factory=list)
    is_complete: bool = False

    def point_at_frame(self, frame_index: int) -> TrackPoint | None:
        """Binary-search for the TrackPoint at a given frame index."""
        lo, hi = 0, len(self.points) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            fi = self.points[mid].frame_index
            if fi == frame_index:
                return self.points[mid]
            elif fi < frame_index:
                lo = mid + 1
            else:
                hi = mid - 1
        return None


# ── Tracker protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class TrackerProtocol(Protocol):
    """
    Minimum interface any tracking backend must satisfy.

    Implementors
    ------------
    - ``engine.tracking.synthetic.SyntheticTracker`` (demo / test)
    - ``services.worker.adapters.sam_adapter.SamTracker``  (production)
    """

    def track(
        self,
        video_path: str,
        *,
        category_filter: Sequence[str] | None = None,
        min_confidence: float = 0.4,
    ) -> list[Track]:
        """
        Run tracking on a video file and return all detected tracks.

        Parameters
        ----------
        video_path : absolute path to the source video file.
        category_filter : if provided, only return tracks whose dominant
            label is in this list.
        min_confidence : drop any detection below this confidence.

        Returns
        -------
        List of Track objects sorted by the frame of first detection.
        """
        ...

"""
engine/tracking/ground_contact.py
──────────────────────────────────
Projects each TrackPoint's ground-contact pixel through the homography to
produce a real-world position with an associated uncertainty interval.

Uncertainty has five named sources (from ARCHITECTURE.md):
  1. pixel_localisation  – sub-pixel uncertainty in the bounding box edge
  2. homography_fit      – residual reprojection error of the calibration
  3. ground_plane_tilt   – vehicle height causes parallax when the scene is
                           not perfectly flat (conservatively estimated)
  4. timestamp_precision – frame timestamp jitter (VFR clips)
  5. detector_confidence – inverse of detection confidence

Each source contributes an independent variance; they are summed and the
square root gives the 1-sigma position uncertainty in metres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.geometry.homography import HomographyResult, PixelPoint, WorldPoint
from engine.geometry.scale import ScaleResult
from engine.tracking.protocols import Track

# ── Result types ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GroundPosition:
    """World-plane position with uncertainty for a single TrackPoint."""

    world: WorldPoint
    sigma_m: float  # 1-sigma position uncertainty (metres)
    pixel_source: tuple[float, float]  # the raw ground-contact pixel used
    frame_index: int
    presentation_ts_s: float

    # Per-source uncertainty breakdown (metres, 1-sigma)
    u_pixel_localisation: float = 0.0
    u_homography_fit: float = 0.0
    u_ground_plane_tilt: float = 0.0
    u_timestamp_precision: float = 0.0
    u_detector_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class GroundTrajectory:
    """
    Sequence of world-plane positions for one object track, plus the
    scale that was used (or None if the trajectory is pixel-only).

    Rules:
    - positions are always produced (pixel-space projection always works).
    - speed_available is False when scale is None.
    - Callers must not compute speed when speed_available is False.
    """

    track_id: str
    positions: list[GroundPosition]
    scale: ScaleResult | None

    @property
    def speed_available(self) -> bool:
        return self.scale is not None


# ── Configuration ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProjectionConfig:
    """Tuning parameters for the uncertainty model."""

    # Estimated ground-contact pixel localisation error (pixels, 1-sigma)
    pixel_localisation_sigma_px: float = 2.0

    # Assumed object height for parallax estimation when scene is not flat (m)
    assumed_object_height_m: float = 1.5

    # Fraction of assumed height used as ground-plane tilt correction factor
    ground_plane_tilt_fraction: float = 0.05

    # Timestamp jitter for VFR clips (seconds)
    vfr_timestamp_jitter_s: float = 0.033  # ≈ 1 frame at 30 fps


# ── Core projection ────────────────────────────────────────────────────────────


def project_track(
    track: Track,
    homography: HomographyResult,
    scale: ScaleResult | None,
    cfg: ProjectionConfig | None = None,
) -> GroundTrajectory:
    """
    Project every TrackPoint in *track* to ground-plane world coordinates.

    When *scale* is None the positions are still computed (in the arbitrary
    world units of the homography), but GroundTrajectory.speed_available
    will be False and the caller must not derive metres/second values.

    Parameters
    ----------
    track : the trajectory to project.
    homography : fitted HomographyResult from estimate_homography().
    scale : optional ScaleResult.  Pass None if calibration is incomplete.
    cfg : uncertainty model parameters.

    Returns
    -------
    GroundTrajectory
    """
    if cfg is None:
        cfg = ProjectionConfig()

    positions: list[GroundPosition] = []

    for tp in track.points:
        gx, gy = tp.bbox.ground_contact_px

        # ── Uncertainty source 1: pixel localisation ─────────────────────────
        # How much does the world position move when the pixel shifts by
        # cfg.pixel_localisation_sigma_px in each direction?
        dx_world = _world_delta_for_pixel_delta(
            homography, gx, gy, cfg.pixel_localisation_sigma_px, 0.0
        )
        dy_world = _world_delta_for_pixel_delta(
            homography, gx, gy, 0.0, cfg.pixel_localisation_sigma_px
        )
        u_pix = math.sqrt(dx_world**2 + dy_world**2)

        # ── Uncertainty source 2: homography reprojection residual ───────────
        # Scale the per-pixel RMSE into metres using the scale factor
        # (or leave in homography units if scale is unavailable)
        rmse_px = homography.reprojection_rmse_px
        mpp = scale.metres_per_pixel if scale is not None else 1.0
        u_hom = rmse_px * mpp

        # ── Uncertainty source 3: ground-plane tilt / vehicle height ─────────
        # A vehicle of height h introduces a parallax error ≈ h * tilt_fraction
        u_tilt = cfg.assumed_object_height_m * cfg.ground_plane_tilt_fraction

        # ── Uncertainty source 4: timestamp precision ─────────────────────────
        u_ts = 0.0  # populated when speed is computed (Phase 4)

        # ── Uncertainty source 5: detector confidence ─────────────────────────
        # Low confidence → higher position uncertainty (ad-hoc factor)
        conf = max(tp.detection_confidence, 1e-3)
        u_det = u_pix * (1.0 - conf)

        # Combined 1-sigma (independent sources → quadrature sum)
        sigma = math.sqrt(u_pix**2 + u_hom**2 + u_tilt**2 + u_ts**2 + u_det**2)

        world = homography.pixel_to_world(PixelPoint(x=gx, y=gy))
        positions.append(
            GroundPosition(
                world=world,
                sigma_m=sigma,
                pixel_source=(gx, gy),
                frame_index=tp.frame_index,
                presentation_ts_s=tp.presentation_ts_s,
                u_pixel_localisation=u_pix,
                u_homography_fit=u_hom,
                u_ground_plane_tilt=u_tilt,
                u_timestamp_precision=u_ts,
                u_detector_confidence=u_det,
            )
        )

    return GroundTrajectory(track_id=track.track_id, positions=positions, scale=scale)


# ── Internal helpers ───────────────────────────────────────────────────────────


def _world_delta_for_pixel_delta(
    hom: HomographyResult,
    px: float,
    py: float,
    dpx: float,
    dpy: float,
) -> float:
    """
    Finite-difference estimate of how much the world position changes
    when the pixel moves by (dpx, dpy).  Returns Euclidean world distance.
    """
    w0 = hom.pixel_to_world(PixelPoint(x=px, y=py))
    w1 = hom.pixel_to_world(PixelPoint(x=px + dpx, y=py + dpy))
    return math.sqrt((w1.x - w0.x) ** 2 + (w1.y - w0.y) ** 2)

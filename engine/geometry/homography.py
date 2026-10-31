"""
engine/geometry/homography.py
─────────────────────────────
Direct Linear Transform (DLT) homography estimation from 2-D pixel
correspondences to real-world ground-plane coordinates.

Design constraints (from ARCHITECTURE.md):
  - No FastAPI / Celery / browser imports.
  - Returns structured results with explicit uncertainty.
  - Raises ValueError with a human-readable message rather than silently
    returning garbage when the input is degenerate.

Reference: Hartley & Zisserman, "Multiple View Geometry in Computer Vision",
           Chapter 4 (DLT) and Chapter 2 (normalisation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

# ── Public types ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PixelPoint:
    """Image-space point (column, row)."""

    x: float  # column (right +)
    y: float  # row    (down  +)


@dataclass(frozen=True, slots=True)
class WorldPoint:
    """Ground-plane world point in metres (origin arbitrary)."""

    x: float  # east  +
    y: float  # north +


@dataclass(frozen=True, slots=True)
class HomographyResult:
    """
    Outcome of DLT estimation.

    Attributes
    ----------
    H : (3, 3) float64 array – the estimated homography (pixel → world).
    reprojection_rmse_px : Root-mean-square reprojection error in *pixels*.
        Computed by projecting world points back through H⁻¹ and measuring
        Euclidean distance to the original pixel observations.
    condition_number : Condition number of the DLT coefficient matrix.
        Values > 1 000 indicate near-degenerate configurations.
    anchor_count : Number of anchors used to fit H.
    """

    H: NDArray[np.float64]
    reprojection_rmse_px: float
    condition_number: float
    anchor_count: int

    def pixel_to_world(self, px: PixelPoint) -> WorldPoint:
        """Project a pixel through H into ground-plane world coordinates."""
        v = self.H @ np.array([px.x, px.y, 1.0], dtype=np.float64)
        return WorldPoint(x=float(v[0] / v[2]), y=float(v[1] / v[2]))

    def world_to_pixel(self, wp: WorldPoint) -> PixelPoint:
        """Back-project a world point through H⁻¹ into pixel coordinates."""
        H_inv = np.linalg.inv(self.H)
        v = H_inv @ np.array([wp.x, wp.y, 1.0], dtype=np.float64)
        return PixelPoint(x=float(v[0] / v[2]), y=float(v[1] / v[2]))


# ── Internal helpers ───────────────────────────────────────────────────────────


def _normalise_points(
    pts: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """
    Isotropic normalisation (Hartley 1997).

    Returns (pts_normalised, T) where T is the (3×3) normalisation matrix
    such that pts_normalised = (T @ [pts | 1]ᵀ)[:2, :].
    """
    centroid = pts.mean(axis=0)
    shifted = pts - centroid
    mean_dist = np.sqrt((shifted**2).sum(axis=1)).mean()
    if mean_dist < 1e-10:
        raise ValueError("Anchor points are all coincident — cannot normalise.")
    scale = math.sqrt(2.0) / mean_dist
    T = np.array(
        [
            [scale, 0.0, -scale * centroid[0]],
            [0.0, scale, -scale * centroid[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    ones = np.ones((len(pts), 1), dtype=np.float64)
    normalised = (T @ np.hstack([pts, ones]).T).T[:, :2]
    return normalised, T


def _build_dlt_matrix(
    src: NDArray[np.float64],  # (N, 2) normalised pixel
    dst: NDArray[np.float64],  # (N, 2) normalised world
) -> NDArray[np.float64]:
    """
    Build the (2N × 9) DLT coefficient matrix A such that A @ h = 0,
    where h = H.ravel().
    """
    N = len(src)
    A = np.zeros((2 * N, 9), dtype=np.float64)
    for i, ((px, py), (wx, wy)) in enumerate(zip(src, dst)):
        # Row 2i   : world-x equation
        A[2 * i] = [-px, -py, -1.0, 0.0, 0.0, 0.0, wx * px, wx * py, wx]
        # Row 2i+1 : world-y equation
        A[2 * i + 1] = [0.0, 0.0, 0.0, -px, -py, -1.0, wy * px, wy * py, wy]
    return A


# ── Public API ─────────────────────────────────────────────────────────────────


MIN_ANCHORS = 4


def estimate_homography(
    pixel_points: Sequence[PixelPoint],
    world_points: Sequence[WorldPoint],
) -> HomographyResult:
    """
    Estimate the ground-plane homography H (pixel → world) from at least
    four non-collinear anchor correspondences using normalised DLT.

    Parameters
    ----------
    pixel_points : observed pixel locations (column, row).
    world_points : corresponding real-world ground-plane positions (metres).

    Returns
    -------
    HomographyResult

    Raises
    ------
    ValueError
        If fewer than 4 anchors are supplied, if points are collinear, or
        if the SVD fails to converge.
    """
    n = len(pixel_points)
    if n < MIN_ANCHORS:
        raise ValueError(
            f"At least {MIN_ANCHORS} anchor correspondences are required for DLT; got {n}."
        )
    if n != len(world_points):
        raise ValueError(
            f"pixel_points ({n}) and world_points ({len(world_points)}) must have the same length."
        )

    px = np.array([[p.x, p.y] for p in pixel_points], dtype=np.float64)
    wx = np.array([[w.x, w.y] for w in world_points], dtype=np.float64)

    # Normalise both point sets (improves numerical conditioning)
    px_n, T_px = _normalise_points(px)
    wx_n, T_wx = _normalise_points(wx)

    A = _build_dlt_matrix(px_n, wx_n)
    if np.linalg.matrix_rank(A, tol=1e-10) < 8:
        raise ValueError("Anchors are degenerate; choose four spread-out, non-collinear points.")

    # Solve via SVD: h is the right singular vector corresponding to the
    # smallest singular value of A.
    try:
        _, S, Vt = np.linalg.svd(A, full_matrices=True)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"SVD failed to converge: {exc}") from exc

    condition_number = float(S[0] / S[-1]) if S[-1] > 1e-12 else float("inf")

    h = Vt[-1].reshape(3, 3)

    # De-normalise: H_real = T_wx⁻¹ @ H_norm @ T_px
    H = np.linalg.inv(T_wx) @ h @ T_px

    # Normalise so that H[2,2] = 1 (scale ambiguity)
    if abs(H[2, 2]) < 1e-12:
        raise ValueError("Calibration is unstable; choose better-spaced anchors.")
    H /= H[2, 2]
    if not np.all(np.isfinite(H)):
        raise ValueError("Calibration produced non-finite values.")

    # ── Reprojection error (in original pixel space) ───────────────────────────
    H_inv = np.linalg.inv(H)
    errors_sq: list[float] = []
    for pp, wp in zip(pixel_points, world_points):
        # Project world → pixel via H⁻¹
        v = H_inv @ np.array([wp.x, wp.y, 1.0], dtype=np.float64)
        reproj = PixelPoint(x=float(v[0] / v[2]), y=float(v[1] / v[2]))
        errors_sq.append((reproj.x - pp.x) ** 2 + (reproj.y - pp.y) ** 2)

    rmse = math.sqrt(sum(errors_sq) / len(errors_sq))

    return HomographyResult(
        H=H,
        reprojection_rmse_px=rmse,
        condition_number=condition_number,
        anchor_count=n,
    )


def reprojection_errors_px(
    result: HomographyResult, pixel_points: Sequence[PixelPoint], world_points: Sequence[WorldPoint]
) -> list[float]:
    """
    Per-anchor reprojection errors in pixels (unsigned Euclidean distance).
    Useful for identifying outlier anchors in the calibration UI.
    """
    H_inv = np.linalg.inv(result.H)
    errors = []
    for pp, wp in zip(pixel_points, world_points):
        v = H_inv @ np.array([wp.x, wp.y, 1.0], dtype=np.float64)
        rx, ry = float(v[0] / v[2]), float(v[1] / v[2])
        errors.append(math.sqrt((rx - pp.x) ** 2 + (ry - pp.y) ** 2))
    return errors

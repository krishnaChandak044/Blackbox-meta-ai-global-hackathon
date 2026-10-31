"""
engine/geometry/scale.py
────────────────────────
Scale estimation from a known-distance pair in the image.

The refusal rule lives here: if no valid calibration exists, this module
raises ScaleUnavailable rather than returning a guess.  Callers MUST catch
this and propagate it to the UI as "speed not computable".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.geometry.homography import HomographyResult, PixelPoint


class ScaleUnavailable(Exception):
    """
    Raised when an absolute scale factor cannot be produced.

    Attributes
    ----------
    reason : machine-readable tag for the UI to localise.
    detail : human-readable explanation shown to the investigator.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


# ── Result types ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ScaleResult:
    """
    Metres-per-pixel scale derived from a calibrated homography.

    Attributes
    ----------
    metres_per_pixel : average ground-plane scale at the reference distance.
    reference_distance_m : the known-distance value used for validation.
    measured_distance_m : distance computed via the homography (should ≈ reference).
    relative_error : |measured − reference| / reference.  > 0.05 is suspicious.
    source : how the scale was obtained, e.g. "homography_anchor_pair".
    """

    metres_per_pixel: float
    reference_distance_m: float
    measured_distance_m: float
    relative_error: float
    source: str


# ── Public API ─────────────────────────────────────────────────────────────────

MAX_ACCEPTABLE_RELATIVE_ERROR = 0.10  # 10 % tolerance


def derive_scale(
    homography: HomographyResult,
    anchor_a_px: PixelPoint,
    anchor_b_px: PixelPoint,
    known_distance_m: float,
) -> ScaleResult:
    """
    Validate the homography scale against a known real-world distance.

    The two pixel anchors are projected to world coordinates and the
    Euclidean world distance is compared to `known_distance_m`.

    Raises
    ------
    ScaleUnavailable
        If the homography has not been provided, if the known distance is
        non-positive, or if the relative error exceeds MAX_ACCEPTABLE_RELATIVE_ERROR.
    """
    if known_distance_m <= 0:
        raise ScaleUnavailable(
            reason="invalid_reference",
            detail="Known distance must be a positive number of metres.",
        )

    w_a = homography.pixel_to_world(anchor_a_px)
    w_b = homography.pixel_to_world(anchor_b_px)

    measured = math.sqrt((w_a.x - w_b.x) ** 2 + (w_a.y - w_b.y) ** 2)
    if measured < 1e-6:
        raise ScaleUnavailable(
            reason="zero_measured_distance",
            detail=(
                "The two reference pixels project to the same world point. "
                "Choose anchors that are further apart."
            ),
        )

    rel_err = abs(measured - known_distance_m) / known_distance_m

    if rel_err > MAX_ACCEPTABLE_RELATIVE_ERROR:
        raise ScaleUnavailable(
            reason="scale_error_too_large",
            detail=(
                f"Homography scale error is {rel_err:.1%}, which exceeds the "
                f"{MAX_ACCEPTABLE_RELATIVE_ERROR:.0%} tolerance. "
                "Check anchor placements or add more anchors."
            ),
        )

    # Average pixel distance in image space
    px_dist = math.sqrt((anchor_a_px.x - anchor_b_px.x) ** 2 + (anchor_a_px.y - anchor_b_px.y) ** 2)
    mpp = known_distance_m / px_dist if px_dist > 0 else float("inf")

    return ScaleResult(
        metres_per_pixel=mpp,
        reference_distance_m=known_distance_m,
        measured_distance_m=measured,
        relative_error=rel_err,
        source="homography_anchor_pair",
    )


def require_scale(scale: ScaleResult | None) -> ScaleResult:
    """
    Guard: raise ScaleUnavailable if scale has not been computed.

    Call this at the top of any function that needs absolute speed or
    distance output.  Never pass ``None`` downstream silently.
    """
    if scale is None:
        raise ScaleUnavailable(
            reason="no_calibration",
            detail=(
                "No ground-plane calibration has been completed for this clip. "
                "Absolute speed and distance values are not available."
            ),
        )
    return scale

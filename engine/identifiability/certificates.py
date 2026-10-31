"""
engine/identifiability/certificates.py
────────────────────────────────────────
Identifiability certificates per derived quantity.

status:
  measurable      — recoverable from current evidence within stated interval
  conditional     — requires an additional assumption (listed in `condition`)
  not_identifiable— cannot be determined from available footage

interval_type:
  illustrative_range — MC spread under listed assumptions; coverage NOT validated
  percentile_range   — only valid after G5 evaluation against held-out scenarios
  not_available      — quantity is not_identifiable
"""

from __future__ import annotations

from engine.dynamics.models import (
    FitQuality,
    IdentifiabilityCertificate,
    UncertaintyBundle,
)


def certify_quantities(
    calibration: dict,
    n_obs: int,
    fit_quality: FitQuality,
    two_seg_used: bool,
    uncertainty: UncertaintyBundle,
    braking_onset_supported: bool = False,
) -> dict[str, IdentifiabilityCertificate]:
    """
    Return a mapping of quantity-name → IdentifiabilityCertificate.

    Quantities certified:
      entry_speed, mean_deceleration, braking_onset, stopping_distance
    """
    certs: dict[str, IdentifiabilityCertificate] = {}
    has_scale = (
        calibration.get("metres_per_pixel") is not None
        and calibration.get("scale_relative_error") is not None
    )
    has_hom = calibration.get("homography_rmse_px") is not None
    fit_ok = fit_quality.converged and fit_quality.reduced_chi_squared < 10.0
    enough_obs = n_obs >= 8

    # ── Entry speed ──────────────────────────────────────────────────────────
    if not has_scale:
        certs["entry_speed"] = IdentifiabilityCertificate(
            quantity="entry_speed",
            status="not_identifiable",
            interval_type="not_available",
            condition=None,
            reason="Scale calibration absent — cannot convert pixels to SI speed",
            limiting_source="scale_calibration",
            improving_observation="Known-distance ground measurement at the scene",
        )
    elif not has_hom:
        certs["entry_speed"] = IdentifiabilityCertificate(
            quantity="entry_speed",
            status="conditional",
            interval_type="illustrative_range",
            condition="homography_reprojection_rmse required but missing",
            reason="Homography fit metadata absent; reprojection error unknown",
            limiting_source="homography_reprojection",
            improving_observation="Re-run homography calibration and record RMSE",
        )
    elif not enough_obs:
        certs["entry_speed"] = IdentifiabilityCertificate(
            quantity="entry_speed", status="conditional", interval_type="illustrative_range",
            condition="at least 8 observations are needed for the current fit policy",
            reason=f"Only {n_obs} observations are available.", limiting_source="model_assumption",
            improving_observation="Add more timestamped, calibrated track observations",
        )
    elif not fit_ok:
        certs["entry_speed"] = IdentifiabilityCertificate(
            quantity="entry_speed",
            status="conditional",
            interval_type="illustrative_range",
            condition="fit_quality: reduced_chi_squared > 10 or did not converge",
            reason=f"Fit quality poor: χ²_r={fit_quality.reduced_chi_squared:.2f}, "
                   f"converged={fit_quality.converged}",
            limiting_source="model_assumption",
            improving_observation="More track observations or a refined motion model",
        )
    else:
        # Determine dominant uncertainty source
        sigmas = {
            "pixel_localisation": uncertainty.pixel_localisation.sigma_metres_or_ms,
            "homography_reprojection": uncertainty.homography_reprojection.sigma_metres_or_ms,
            "scale_calibration": uncertainty.scale_calibration.sigma_metres_or_ms,
            "frame_timestamp": uncertainty.frame_timestamp.sigma_metres_or_ms,
            "model_assumption": uncertainty.model_assumption.sigma_metres_or_ms,
        }
        dom = max(sigmas, key=sigmas.get)
        certs["entry_speed"] = IdentifiabilityCertificate(
            quantity="entry_speed",
            status="measurable",
            interval_type="illustrative_range",
            condition=None,
            reason="Calibration present, fit converged, sufficient observations",
            limiting_source=dom,
            improving_observation=_improving_obs(dom),
        )

    # ── Mean deceleration ────────────────────────────────────────────────────
    if not two_seg_used:
        certs["mean_deceleration"] = IdentifiabilityCertificate(
            quantity="mean_deceleration",
            status="not_identifiable",
            interval_type="not_available",
            condition=None,
            reason="Single-segment fit selected; no supported deceleration change-point detected. "
                   "Cannot infer deceleration from a trajectory consistent with constant acceleration.",
            limiting_source="model_assumption",
            improving_observation="Track spanning visible braking event with ≥10 observations",
        )
    elif not braking_onset_supported:
        certs["mean_deceleration"] = IdentifiabilityCertificate(
            quantity="mean_deceleration", status="not_identifiable", interval_type="not_available",
            condition=None, reason="No deceleration change-point passed the current fit policy.",
            limiting_source="model_assumption", improving_observation="Record a longer track spanning visible slowing",
        )
    elif not fit_ok or not enough_obs:
        certs["mean_deceleration"] = IdentifiabilityCertificate(
            quantity="mean_deceleration",
            status="conditional",
            interval_type="illustrative_range",
            condition="fit convergence required",
            reason="Two-segment fit used but convergence or quality is poor",
            limiting_source="model_assumption",
            improving_observation="Higher frame rate or denser track observations",
        )
    else:
        certs["mean_deceleration"] = IdentifiabilityCertificate(
            quantity="mean_deceleration",
            status="measurable",
            interval_type="illustrative_range",
            condition=None,
            reason="Two-segment fit converged with supported change-point",
            limiting_source="model_assumption",
            improving_observation="Known road friction coefficient measurement",
        )

    # ── Braking onset ────────────────────────────────────────────────────────
    if not braking_onset_supported or not enough_obs:
        certs["braking_onset"] = IdentifiabilityCertificate(
            quantity="braking_onset",
            status="not_identifiable",
            interval_type="not_available",
            condition=None,
            reason="A deceleration change-point is not supported with the current observation count and fit diagnostics",
            limiting_source="model_assumption",
            improving_observation="Track with visible speed reduction spanning ≥5 frames",
        )
    else:
        certs["braking_onset"] = IdentifiabilityCertificate(
            quantity="braking_onset",
            status="conditional",
            interval_type="illustrative_range",
            condition="piecewise constant-acceleration model and tested breakpoint grid",
            reason="A candidate deceleration change-point passed model selection; its coverage is not calibrated",
            limiting_source="model_assumption",
            improving_observation="Higher frame-rate observations around the candidate onset",
        )

    # ── Stopping distance ────────────────────────────────────────────────────
    if certs["entry_speed"].status == "not_identifiable" or \
       certs["mean_deceleration"].status == "not_identifiable":
        certs["stopping_distance"] = IdentifiabilityCertificate(
            quantity="stopping_distance",
            status="not_identifiable",
            interval_type="not_available",
            condition=None,
            reason="Requires both entry_speed and mean_deceleration to be measurable",
            limiting_source=None,
            improving_observation="See entry_speed and mean_deceleration certificates",
        )
    else:
        certs["stopping_distance"] = IdentifiabilityCertificate(
            quantity="stopping_distance",
            status="conditional",
            interval_type="illustrative_range",
            condition="constant deceleration assumed throughout stop; road level and dry",
            reason="Stopping distance derived from v²/2a model under stated assumptions",
            limiting_source="model_assumption",
            improving_observation="Track data spanning the actual stop event",
        )

    return certs


def _improving_obs(dominant_source: str) -> str:
    return {
        "pixel_localisation": "Higher-resolution camera or manual keypoint marking per frame",
        "homography_reprojection": "Additional calibration anchors from the scene geometry",
        "scale_calibration": "On-scene known-distance measurement with survey equipment",
        "frame_timestamp": "Camera firmware log or GPS-synchronized timecode",
        "model_assumption": "IMU data for actual acceleration profile",
    }.get(dominant_source, "Additional field measurements")

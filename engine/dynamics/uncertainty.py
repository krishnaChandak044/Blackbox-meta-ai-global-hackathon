"""
engine/dynamics/uncertainty.py
──────────────────────────────
Five-source seeded Monte Carlo uncertainty propagation.
Framework-free: NumPy only.

Five sources (tracked separately, never collapsed silently):
  1. pixel_localisation    — tracker box placement uncertainty
  2. homography_reprojection — error in the ground-plane mapping
  3. scale_calibration     — relative error of the known-distance measurement
  4. frame_timestamp       — VFR jitter / PTS precision
  5. model_assumption      — constant-acceleration vs real kinematics
"""

from __future__ import annotations

import numpy as np

from engine.dynamics.models import (
    IntervalType,
    UncertaintyBundle,
    UncertaintyContribution,
)

_PERCENTILE_LO = 5.0
_PERCENTILE_HI = 95.0


def propagate_uncertainty(
    calibration: dict,
    vfr_meta: dict,
    sigmas_m: np.ndarray,
    speeds_ms: np.ndarray,
    seed: int = 42,
    n_samples: int = 1000,
    timestamps_s: np.ndarray | None = None,
    frame_timestamp_sigma_s: float | None = None,
) -> UncertaintyBundle:
    """
    Propagate all 5 uncertainty sources into a combined speed interval.

    Returns an UncertaintyBundle with:
    - Each source as a separate UncertaintyContribution
    - combined_lo / combined_hi as 5th/95th percentile of Monte Carlo samples
    - interval_type = "illustrative_range" (not "95% CI" — coverage not validated)
    """
    rng = np.random.default_rng(seed)
    mpp = float(calibration.get("metres_per_pixel", 0.05))
    hmse_px = float(calibration.get("homography_rmse_px", 2.0))
    scale_rerr = float(calibration.get("scale_relative_error", 0.05))
    frame_sigma_s = float(
        frame_timestamp_sigma_s
        if frame_timestamp_sigma_s is not None
        else vfr_meta.get("frame_duration_sigma_s", 0.0)
    )

    mean_speed = float(np.mean(speeds_ms)) if len(speeds_ms) else 10.0

    # ── 1. Pixel localisation ────────────────────────────────────────────────
    # sigma_m = tracker RMS in pixels × metres_per_pixel
    sigma_pix_m = float(np.mean(sigmas_m))
    # Effect on speed: uncertainty in position over dt
    dts = np.diff(timestamps_s) if timestamps_s is not None and len(timestamps_s) > 1 else np.array([])
    mean_dt = float(np.median(dts)) if len(dts) else 0.0
    if mean_dt <= 0:
        raise ValueError("Cannot propagate uncertainty without positive measured frame intervals")
    sigma_speed_pix = np.sqrt(2.0) * sigma_pix_m / mean_dt

    contrib_pixel = UncertaintyContribution(
        source="pixel_localisation",
        sigma_metres_or_ms=float(sigma_speed_pix),
        distribution="gaussian",
        metadata=f"tracker_sigma_m={sigma_pix_m:.4f}, metres_per_pixel={mpp:.5f}",
        propagation_method=f"Monte Carlo N={n_samples} seed={seed}",
    )

    # ── 2. Homography reprojection ───────────────────────────────────────────
    sigma_hom_m = hmse_px * mpp
    sigma_speed_hom = np.sqrt(2.0) * sigma_hom_m / mean_dt

    contrib_hom = UncertaintyContribution(
        source="homography_reprojection",
        sigma_metres_or_ms=float(sigma_speed_hom),
        distribution="gaussian",
        metadata=f"homography_rmse_px={hmse_px:.2f}, metres_per_pixel={mpp:.5f}",
        propagation_method=f"Monte Carlo N={n_samples} seed={seed}",
    )

    # ── 3. Scale calibration ─────────────────────────────────────────────────
    sigma_speed_scale = mean_speed * scale_rerr

    contrib_scale = UncertaintyContribution(
        source="scale_calibration",
        sigma_metres_or_ms=float(sigma_speed_scale),
        distribution="gaussian",
        metadata=f"scale_relative_error={scale_rerr:.4f}",
        propagation_method=f"Monte Carlo N={n_samples} seed={seed}",
    )

    # ── 4. Frame timestamp ───────────────────────────────────────────────────
    # Speed ≈ Δx / Δt, so uncertainty in Δt → σ_speed ≈ mean_speed × (σ_t / dt)
    sigma_speed_ts = mean_speed * (np.sqrt(2.0) * frame_sigma_s / mean_dt)

    contrib_ts = UncertaintyContribution(
        source="frame_timestamp",
        sigma_metres_or_ms=float(sigma_speed_ts),
        distribution="gaussian",
        metadata=(f"frame_duration_sigma_s={frame_sigma_s:.6f}; "
                  f"{vfr_meta.get('timestamp_metadata', 'camera clock accuracy unknown')}"),
        propagation_method=f"Monte Carlo N={n_samples} seed={seed}",
    )

    # ── 5. Model assumption ──────────────────────────────────────────────────
    # Constant acceleration: allow ±2 m/s deviation from true speed
    sigma_model = float(vfr_meta.get("model_speed_bound_ms", 2.0))

    contrib_model = UncertaintyContribution(
        source="model_assumption",
        sigma_metres_or_ms=sigma_model,
        distribution="uniform",
        metadata=f"declared model discrepancy bound ±{sigma_model:.3f} m/s; illustrative only",
        propagation_method="uniform sensitivity bound — not empirically calibrated",
    )

    # ── Monte Carlo combination ──────────────────────────────────────────────
    # Each source contributes an independent Gaussian perturbation to speed
    mc_pix = rng.normal(0, sigma_speed_pix, n_samples)
    mc_hom = rng.normal(0, sigma_speed_hom, n_samples)
    mc_scale = rng.normal(0, sigma_speed_scale, n_samples)
    mc_ts = rng.normal(0, sigma_speed_ts, n_samples)
    mc_model = rng.uniform(-sigma_model, sigma_model, n_samples)

    mc_total = mean_speed + mc_pix + mc_hom + mc_scale + mc_ts + mc_model
    combined_lo = float(np.percentile(mc_total, _PERCENTILE_LO))
    combined_hi = float(np.percentile(mc_total, _PERCENTILE_HI))

    return UncertaintyBundle(
        pixel_localisation=contrib_pixel,
        homography_reprojection=contrib_hom,
        scale_calibration=contrib_scale,
        frame_timestamp=contrib_ts,
        model_assumption=contrib_model,
        combined_lo=combined_lo,
        combined_hi=combined_hi,
        interval_type="illustrative_range",
        seed=seed,
        n_samples=n_samples,
    )

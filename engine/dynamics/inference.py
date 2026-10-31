"""
engine/dynamics/inference.py
─────────────────────────────
Deterministic piecewise-constant-acceleration fit over a vehicle track.
Framework-free: NumPy + SciPy only.

Contract
────────
- Returns a typed DynamicsResult.
- Rejects/returns not_identifiable on: missing calibration, non-monotonic
  timestamps, too few observations, missing uncertainty metadata.
- Never fills missing observations as if measured.
- All smoothing is marked as model output (not raw data).
- Does NOT accept or use Phase 3 witness statements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from engine.dynamics.models import (
    BrakingOnset,
    DynamicsResult,
    FitQuality,
    FittedPoint,
    IdentifiabilityCertificate,
    UncertaintyBundle,
)
from engine.dynamics.uncertainty import propagate_uncertainty
from engine.identifiability.certificates import certify_quantities

# ── Model version ─────────────────────────────────────────────────────────────
MODEL_NAME = "piecewise_const_accel_2d_v1"
MODEL_VERSION = "1.0.0"


# ── Eligibility checks ────────────────────────────────────────────────────────

class InferenceRejected(Exception):
    """Raised when inputs do not meet eligibility criteria."""


def _check_eligibility(
    observations: list[dict[str, Any]],
    calibration: dict[str, Any],
    vfr_meta: dict[str, Any],
    params: dict[str, Any],
) -> None:
    """
    Raise InferenceRejected with a machine-readable reason if inputs are invalid.
    Never silently coerce bad inputs.
    """
    if not calibration:
        raise InferenceRejected("calibration_absent: no homography/scale provided")

    scale = calibration.get("metres_per_pixel")
    if scale is None or not (0 < scale < 100):
        raise InferenceRejected(f"calibration_invalid: metres_per_pixel={scale!r}")

    if calibration.get("homography_rmse_px") is None:
        raise InferenceRejected("calibration_incomplete: homography_rmse_px missing")

    if calibration.get("scale_relative_error") is None:
        raise InferenceRejected("calibration_incomplete: scale_relative_error missing")

    if not observations:
        raise InferenceRejected("track_empty: no observations")

    if len(observations) < 5:
        raise InferenceRejected(
            f"insufficient_observations: need ≥5, got {len(observations)}"
        )

    # Monotonic timestamps
    ts = [o.get("presentation_ts_s") for o in observations]
    if any(t is None for t in ts):
        raise InferenceRejected("timestamps_missing: some observations lack presentation_ts_s")

    ts_arr = np.array(ts, dtype=float)
    diffs = np.diff(ts_arr)
    if np.any(diffs <= 0):
        raise InferenceRejected(
            f"timestamps_non_monotonic: min_delta={float(diffs.min()):.6f}s"
        )

    # World coordinates
    for i, o in enumerate(observations):
        if o.get("world_x_m") is None or o.get("world_y_m") is None:
            raise InferenceRejected(
                f"world_coords_missing: observation {i} lacks world_x_m / world_y_m. "
                "Units must be in SI metres derived from a valid homography."
            )
        sigma = o.get("localisation_sigma_m")
        if sigma is None or not np.isfinite(float(sigma)) or float(sigma) <= 0:
            raise InferenceRejected(
                f"localisation_uncertainty_missing: observation {i} needs a positive sigma_m"
            )

    if vfr_meta.get("has_vfr") and vfr_meta.get("pts_available") is False:
        raise InferenceRejected(
            "vfr_no_pts: variable frame-rate stream but no presentation timestamps "
            "available from probe — cannot derive reliable time axis"
        )

    # Parameter bounds
    bounds = params.get("bounds", {})
    if not bounds:
        raise InferenceRejected("params_missing: no parameter bounds declared")


# ── Forward model ─────────────────────────────────────────────────────────────

def _piecewise_const_accel(
    t: np.ndarray,
    t0: float,
    x0: float, y0: float,
    vx0: float, vy0: float,
    ax1: float, ay1: float,
    t_break: float | None,
    ax2: float, ay2: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    2-segment piecewise constant acceleration.
    Phase 1: t in [t0, t_break] with (ax1, ay1)
    Phase 2: t in (t_break, end] with (ax2, ay2)
    If t_break is None, single-segment.
    """
    dt = t - t0
    if t_break is None:
        x = x0 + vx0 * dt + 0.5 * ax1 * dt ** 2
        y = y0 + vy0 * dt + 0.5 * ay1 * dt ** 2
    else:
        dt1 = np.clip(dt, 0, t_break - t0)
        dt2 = np.maximum(0, dt - (t_break - t0))
        # velocity at break
        vx_b = vx0 + ax1 * (t_break - t0)
        vy_b = vy0 + ay1 * (t_break - t0)
        xb = x0 + vx0 * (t_break - t0) + 0.5 * ax1 * (t_break - t0) ** 2
        yb = y0 + vy0 * (t_break - t0) + 0.5 * ay1 * (t_break - t0) ** 2
        x = np.where(
            dt <= (t_break - t0),
            x0 + vx0 * dt1 + 0.5 * ax1 * dt1 ** 2,
            xb + vx_b * dt2 + 0.5 * ax2 * dt2 ** 2,
        )
        y = np.where(
            dt <= (t_break - t0),
            y0 + vy0 * dt1 + 0.5 * ay1 * dt1 ** 2,
            yb + vy_b * dt2 + 0.5 * ay2 * dt2 ** 2,
        )
    return x, y


def _residuals_1seg(p, t, obs_x, obs_y, w):
    t0, x0, y0, vx0, vy0, ax, ay = p
    x, y = _piecewise_const_accel(t, t0, x0, y0, vx0, vy0, ax, ay, None, 0, 0)
    return w * np.concatenate([x - obs_x, y - obs_y])


def _residuals_2seg(p, t, obs_x, obs_y, w, t_break):
    t0, x0, y0, vx0, vy0, ax1, ay1, ax2, ay2 = p
    x, y = _piecewise_const_accel(t, t0, x0, y0, vx0, vy0, ax1, ay1, t_break, ax2, ay2)
    return w * np.concatenate([x - obs_x, y - obs_y])


# ── Main inference function ───────────────────────────────────────────────────

def run_inference(
    observations: list[dict[str, Any]],
    calibration: dict[str, Any],
    vfr_meta: dict[str, Any],
    params: dict[str, Any],
    track_id: str,
    track_version_hash: str,
    media_sha256: str,
    software_revision: str,
    seed: int = 42,
) -> DynamicsResult:
    """
    Run piecewise constant-acceleration fit.

    Parameters
    ──────────
    observations : list of dicts with keys:
        frame_index, presentation_ts_s, world_x_m, world_y_m,
        localisation_sigma_m (pixel-localisation uncertainty in metres)
    calibration : dict with keys:
        metres_per_pixel, homography_rmse_px, scale_relative_error,
        homography_fit_id
    vfr_meta : dict with keys:
        has_vfr, pts_available, mean_frame_duration_s, frame_duration_sigma_s
    params : dict with keys:
        bounds (dict), try_two_segment (bool), interval_s (list[float, float])
    """
    _check_eligibility(observations, calibration, vfr_meta, params)

    params_json = json.dumps(params, sort_keys=True, default=str)

    # ── Prepare arrays ────────────────────────────────────────────────────────
    obs = sorted(observations, key=lambda o: o["presentation_ts_s"])
    t = np.array([o["presentation_ts_s"] for o in obs])
    obs_x = np.array([o["world_x_m"] for o in obs])
    obs_y = np.array([o["world_y_m"] for o in obs])
    sigmas = np.array([o["localisation_sigma_m"] for o in obs], dtype=float)
    # Robust weights: inverse sigma, clipped to prevent extreme dominance
    w = np.clip(1.0 / (sigmas + 1e-6), 0.01, 100.0)

    t0_init = t[0]
    x0_init, y0_init = obs_x[0], obs_y[0]

    # Crude velocity estimate from first→last pair
    dt_total = t[-1] - t[0]
    vx0_init = (obs_x[-1] - obs_x[0]) / dt_total if dt_total > 0 else 0.0
    vy0_init = (obs_y[-1] - obs_y[0]) / dt_total if dt_total > 0 else 0.0

    # ── Single-segment fit ────────────────────────────────────────────────────
    p0_1 = [t0_init, x0_init, y0_init, vx0_init, vy0_init, 0.0, 0.0]
    b = params.get("bounds", {})
    max_v = b.get("max_speed_ms", 50.0)
    max_a = b.get("max_accel_ms2", 15.0)
    lo1 = [t[0], -1e4, -1e4, -max_v, -max_v, -max_a, -max_a]
    hi1 = [t[-1], 1e4, 1e4, max_v, max_v, max_a, max_a]

    res1 = least_squares(
        _residuals_1seg, p0_1,
        args=(t, obs_x, obs_y, w),
        bounds=(lo1, hi1),
        method="trf",
        loss="soft_l1",
        max_nfev=5000,
    )

    best_res = res1
    t_break_used: float | None = None
    two_seg_used = False
    best_params_2seg = None

    # ── Optional two-segment fit ──────────────────────────────────────────────
    if params.get("try_two_segment", True) and len(obs) >= 10:
        # Try candidate break points at the 25th, 50th, 75th percentile timestamps
        best_2_cost = np.inf
        for frac in [0.25, 0.40, 0.55, 0.70]:
            t_break_cand = t[0] + frac * (t[-1] - t[0])
            p0_2 = [t0_init, x0_init, y0_init, vx0_init, vy0_init, 0.0, 0.0, -3.0, 0.0]
            lo2 = [t[0], -1e4, -1e4, -max_v, -max_v, -max_a, -max_a, -max_a, -max_a]
            hi2 = [t[-1], 1e4, 1e4, max_v, max_v, max_a, max_a, max_a, max_a]
            try:
                res2 = least_squares(
                    _residuals_2seg, p0_2,
                    args=(t, obs_x, obs_y, w, t_break_cand),
                    bounds=(lo2, hi2),
                    method="trf",
                    loss="soft_l1",
                    max_nfev=5000,
                )
                if res2.cost < best_2_cost:
                    best_2_cost = res2.cost
                    best_params_2seg = res2
                    t_break_used = t_break_cand
            except Exception:
                pass

        # Accept two-segment only if it materially improves the fit (BIC-like)
        n = len(obs) * 2  # both x and y
        bic_1 = n * np.log(res1.cost / n + 1e-12) + 7 * np.log(n)
        bic_2 = n * np.log(best_2_cost / n + 1e-12) + 9 * np.log(n) if best_2_cost < np.inf else np.inf

        if best_params_2seg is not None and bic_2 < bic_1 - 4.0:
            best_res = best_params_2seg
            two_seg_used = True

    # ── Reconstruct fitted points ─────────────────────────────────────────────
    p_fit = best_res.x
    if two_seg_used:
        t0_f, x0_f, y0_f, vx0_f, vy0_f, ax1_f, ay1_f, ax2_f, ay2_f = p_fit
        ax_fn = lambda tt: np.where(tt <= t_break_used, ax1_f, ax2_f)  # noqa: E731
        ay_fn = lambda tt: np.where(tt <= t_break_used, ay1_f, ay2_f)  # noqa: E731
        fit_x, fit_y = _piecewise_const_accel(
            t, t0_f, x0_f, y0_f, vx0_f, vy0_f, ax1_f, ay1_f, t_break_used, ax2_f, ay2_f
        )
    else:
        t0_f, x0_f, y0_f, vx0_f, vy0_f, ax_f, ay_f = p_fit
        ax1_f = ax_f; ay1_f = ay_f; ax2_f = ax_f; ay2_f = ay_f
        ax_fn = lambda tt: np.full_like(tt, ax_f)  # noqa: E731
        ay_fn = lambda tt: np.full_like(tt, ay_f)  # noqa: E731
        fit_x, fit_y = _piecewise_const_accel(t, t0_f, x0_f, y0_f, vx0_f, vy0_f, ax_f, ay_f, None, 0, 0)

    # Velocity at each point (finite-difference of fit)
    dt_arr = np.diff(t, prepend=t[0] - 1e-6)
    dx_fit = np.gradient(fit_x, t)
    dy_fit = np.gradient(fit_y, t)
    speeds_ms = np.sqrt(dx_fit ** 2 + dy_fit ** 2)

    # ── Uncertainty propagation ───────────────────────────────────────────────
    uncertainty = propagate_uncertainty(
        calibration=calibration,
        vfr_meta=vfr_meta,
        sigmas_m=sigmas,
        speeds_ms=speeds_ms,
        seed=seed,
        n_samples=1000,
        timestamps_s=t,
        frame_timestamp_sigma_s=float(vfr_meta.get("frame_duration_sigma_s", 0.0)),
    )

    # ── Fit quality ───────────────────────────────────────────────────────────
    residuals_xy = best_res.fun
    n_res = len(residuals_xy)
    n_obs = len(obs)
    unweighted_residuals = residuals_xy / np.tile(w, 2)
    rmse = float(np.sqrt(np.mean(unweighted_residuals ** 2)))

    # Jacobian → parameter correlation matrix
    covariance = None
    try:
        J = best_res.jac
        JtJ = J.T @ J
        cov = np.linalg.pinv(JtJ)
        diag = np.sqrt(np.abs(np.diag(cov)))
        denom = np.outer(diag, diag)
        corr = np.where(denom > 0, cov / denom, 0.0)
        corr_flat = corr.flatten().tolist()
    except Exception:
        cov = None
        corr_flat = []

    n_params = len(p_fit)
    dof = max(1, n_obs * 2 - n_params)
    chi2r = float(np.sum(best_res.fun ** 2) / dof)
    covariance = cov * chi2r if cov is not None else None

    fit_quality = FitQuality(
        rmse_metres=rmse,
        max_residual_metres=float(np.max(np.abs(unweighted_residuals))),
        n_observations=n_obs,
        n_parameters=n_params,
        converged=best_res.success or best_res.status in (1, 2, 3, 4),
        convergence_message=best_res.message,
        reduced_chi_squared=chi2r,
        param_correlation_flat=corr_flat,
        param_names=list(
            ["t0", "x0", "y0", "vx0", "vy0", "ax1", "ay1", "ax2", "ay2"][:n_params]
        ),
    )

    # Per-frame uncertainty ellipse combines the five declared contributors.
    # Homography pixels are converted with the stored local scale; camera clock
    # accuracy remains unknown and is stated separately in timestamp metadata.
    half_w_ms = (uncertainty.combined_hi - uncertainty.combined_lo) / 2.0
    hom_sigma_m = float(calibration["homography_rmse_px"]) * float(calibration["metres_per_pixel"])
    scale_rel = float(calibration["scale_relative_error"])
    time_sigma = float(vfr_meta.get("frame_duration_sigma_s", 0.0))
    model_pos_sigma = float(np.sqrt(np.mean((fit_x - obs_x) ** 2 + (fit_y - obs_y) ** 2)))
    fitted_points: list[FittedPoint] = []
    origin_x, origin_y = float(obs_x[0]), float(obs_y[0])
    for i, o in enumerate(obs):
        sp_ms = float(speeds_ms[i])
        sp_kmh = sp_ms * 3.6
        # Scale error applies to relative coordinates, not the arbitrary origin.
        pos_x_sigma = float(np.sqrt(
            sigmas[i] ** 2 + hom_sigma_m ** 2
            + ((fit_x[i] - origin_x) * scale_rel) ** 2
            + (dx_fit[i] * time_sigma) ** 2 + model_pos_sigma ** 2
        ))
        pos_y_sigma = float(np.sqrt(
            sigmas[i] ** 2 + hom_sigma_m ** 2
            + ((fit_y[i] - origin_y) * scale_rel) ** 2
            + (dy_fit[i] * time_sigma) ** 2 + model_pos_sigma ** 2
        ))
        fitted_points.append(FittedPoint(
            frame_index=o["frame_index"], presentation_ts_s=float(t[i]),
            world_x_m=float(fit_x[i]), world_y_m=float(fit_y[i]),
            vx_ms=float(dx_fit[i]), vy_ms=float(dy_fit[i]),
            speed_ms=sp_ms, speed_kmh=sp_kmh,
            pos_sigma_x_m=pos_x_sigma, pos_sigma_y_m=pos_y_sigma,
            speed_lo_kmh=max(0.0, sp_ms - half_w_ms) * 3.6,
            speed_hi_kmh=(sp_ms + half_w_ms) * 3.6,
        ))

    # ── Braking onset ─────────────────────────────────────────────────────────
    braking_onset = None
    if two_seg_used and t_break_used is not None:
        dt_break = t_break_used - t0_f
        vx_break = vx0_f + ax1_f * dt_break
        vy_break = vy0_f + ay1_f * dt_break
        speed_break = max(float(np.hypot(vx_break, vy_break)), 1e-9)
        decel_after = max(0.0, -(ax2_f * vx_break + ay2_f * vy_break) / speed_break)
        decel_before = max(0.0, -(ax1_f * vx_break + ay1_f * vy_break) / speed_break)
        if decel_after > decel_before + 0.5 and decel_after > 0.5:
            # Find frame indices bracketing the break
            idx_lo = int(np.searchsorted(t, t_break_used - 0.25))
            idx_hi = int(np.searchsorted(t, t_break_used + 0.25))
            idx_lo = max(0, min(idx_lo, len(obs) - 1))
            idx_hi = max(0, min(idx_hi, len(obs) - 1))
            braking_cert = IdentifiabilityCertificate(
                quantity="braking_onset",
                status="conditional",
                interval_type="illustrative_range",
                condition="piecewise constant acceleration and tested breakpoint grid",
                reason="Candidate deceleration change-point detected; onset interval is not empirically calibrated",
                limiting_source="frame_timestamp",
                improving_observation="Higher frame-rate or closer camera angle",
            )
            braking_onset = BrakingOnset(
                frame_index_lo=obs[idx_lo]["frame_index"],
                frame_index_hi=obs[idx_hi]["frame_index"],
                ts_lo_s=float(t[idx_lo]),
                ts_hi_s=float(t[idx_hi]),
                decel_before_ms2=decel_before,
                decel_after_ms2=decel_after,
                certificate=braking_cert,
            )

    # ── Identifiability certificates ──────────────────────────────────────────
    entry_speed_ms = float(np.sqrt(vx0_f ** 2 + vy0_f ** 2))
    certs = certify_quantities(
        calibration=calibration,
        n_obs=n_obs,
        fit_quality=fit_quality,
        two_seg_used=two_seg_used,
        uncertainty=uncertainty,
        braking_onset_supported=braking_onset is not None,
    )

    # ── Entry speed & mean decel ──────────────────────────────────────────────
    entry_kmh = entry_speed_ms * 3.6
    speed_cert = certs.get("entry_speed", None)
    e_lo = e_hi = None
    if speed_cert and speed_cert.status != "not_identifiable":
        hw = (uncertainty.combined_hi - uncertainty.combined_lo) / 2.0 * 3.6
        e_lo = max(0.0, entry_kmh - hw)
        e_hi = entry_kmh + hw

    d_ms2 = d_lo = d_hi = None
    if two_seg_used and braking_onset is not None:
        d_ms2 = braking_onset.decel_after_ms2
        if covariance is not None and covariance.shape[0] >= 9:
            dt_break = t_break_used - t0_f
            v_break = np.array([vx0_f + ax1_f * dt_break, vy0_f + ay1_f * dt_break])
            v_norm = max(float(np.linalg.norm(v_break)), 1e-9)
            gradient = -v_break / v_norm
            variance = float(gradient @ covariance[7:9, 7:9] @ gradient)
            half = 1.96 * float(np.sqrt(max(variance, 0.0)))
            if np.isfinite(half) and half < max(0.1, d_ms2 * 2.0):
                d_lo, d_hi = max(0.0, d_ms2 - half), d_ms2 + half
            else:
                certs["mean_deceleration"] = IdentifiabilityCertificate(
                    quantity="mean_deceleration", status="conditional", interval_type="illustrative_range",
                    condition="local linear covariance approximation; interval coverage unvalidated",
                    reason="Deceleration point fit exists, but its uncertainty is too broad for a stable interval.",
                    limiting_source="model_assumption", improving_observation="More observations around the braking transition",
                )
                d_ms2 = None
        else:
            certs["mean_deceleration"] = IdentifiabilityCertificate(
                quantity="mean_deceleration", status="conditional", interval_type="illustrative_range",
                condition="parameter covariance was unavailable",
                reason="A deceleration estimate exists but no interval could be computed from fit diagnostics.",
                limiting_source="model_assumption", improving_observation="Add observations spanning the transition",
            )
            d_ms2 = None

    provenance_key = json.dumps({
        "track_id": track_id,
        "track_version_hash": track_version_hash,
        "calibration_fit_id": calibration.get("homography_fit_id", ""),
        "media_sha256": media_sha256,
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "software_revision": software_revision,
        "seed": seed,
        "params": params_json,
    }, sort_keys=True).encode()
    run_id = hashlib.sha256(provenance_key).hexdigest()[:36]

    return DynamicsResult(
        run_id=run_id,
        track_id=track_id,
        track_version_hash=track_version_hash,
        calibration_fit_id=calibration.get("homography_fit_id", ""),
        media_sha256=media_sha256,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        software_revision=software_revision,
        seed=seed,
        params_json=params_json,
        fitted_points=fitted_points,
        entry_speed_kmh=entry_kmh,
        entry_speed_lo_kmh=e_lo,
        entry_speed_hi_kmh=e_hi,
        mean_decel_ms2=d_ms2,
        mean_decel_lo_ms2=d_lo,
        mean_decel_hi_ms2=d_hi,
        braking_onset=braking_onset,
        uncertainty=uncertainty,
        certificates=certs,
        fit_quality=fit_quality,
        interval_type="illustrative_range",
    )

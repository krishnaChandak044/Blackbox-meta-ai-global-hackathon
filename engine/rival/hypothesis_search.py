"""Reproducible, bounded search for alternate 1D speed/deceleration histories."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np

from engine.dynamics.models import RivalHypothesis, RivalManifest, RivalSearchResult

SEARCH_VERSION = "bounded_kinematic_grid_v2"
MATERIALITY_THRESHOLD_KMH = 5.0


def search_rivals(
    primary_run: dict[str, Any],
    observations: list[dict[str, Any]],
    calibration: dict[str, Any],
    params: dict[str, Any] | None = None,
    second_view: dict[str, Any] | None = None,
    seed: int = 42,
) -> RivalSearchResult:
    params = params or {}
    if len(observations) < 5:
        raise ValueError("Rival search needs at least five calibrated observations")
    if not calibration.get("calibrated", True):
        raise ValueError("Rival search requires calibrated world-coordinate observations")
    primary_v = primary_run.get("entry_speed_kmh")
    primary_a = primary_run.get("mean_decel_ms2")
    if primary_v is None:
        raise ValueError("Primary entry speed must be available to bound rival search")
    if primary_a is None:
        primary_a = float(params.get("decel_reference_ms2", 4.0))

    obs = sorted(observations, key=lambda item: item["presentation_ts_s"])
    t0, t1 = obs[0]["presentation_ts_s"], obs[-1]["presentation_ts_s"]
    primary_onset = float(primary_run.get("braking_onset_s", t0))
    n_grid = max(3, min(int(params.get("n_grid", 15)), 40))
    threshold = float(params.get("acceptance_threshold_m", 1.0))
    bounds = {
        "entry_speed_kmh": (float(params.get("speed_lo_kmh", max(0.0, primary_v - 20)),),
                             float(params.get("speed_hi_kmh", primary_v + 20))),
        "deceleration_ms2": (float(params.get("decel_lo_ms2", max(0.1, primary_a - 4)),),
                              float(params.get("decel_hi_ms2", primary_a + 4))),
        "braking_onset_s": (float(params.get("onset_lo_s", t0)),
                             float(params.get("onset_hi_s", t1))),
    }
    for name, (lo, hi) in bounds.items():
        if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
            raise ValueError(f"Invalid rival search bounds for {name}")

    primary_residual = _compute_residual(primary_v, primary_a, primary_onset, obs)
    primary_obs_hash = hashlib.sha256(json.dumps(obs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    second_obs_hash = (
        hashlib.sha256(json.dumps(second_view.get("observations", []), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if second_view else None
    )
    candidates = []
    evaluated = 0
    speeds = np.linspace(*bounds["entry_speed_kmh"], n_grid)
    decels = np.linspace(*bounds["deceleration_ms2"], n_grid)
    onsets = np.linspace(*bounds["braking_onset_s"], n_grid)
    for speed in speeds:
        for decel in decels:
            for onset in onsets:
                material = (
                    abs(float(speed) - primary_v) >= MATERIALITY_THRESHOLD_KMH
                    or abs(float(decel) - primary_a) >= 0.75
                    or abs(float(onset) - primary_onset) >= 0.25
                )
                if not material:
                    continue
                evaluated += 1
                residual = _compute_residual(float(speed), float(decel), float(onset), obs)
                candidates.append((residual, float(speed), float(decel), float(onset)))
    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    accepted: list[RivalHypothesis] = []
    for residual, speed, decel, onset in candidates:
        if residual > threshold or len(accepted) >= 10:
            break
        status, reason, distinguishing = _disambiguate(
            speed, decel, onset, primary_v, primary_a, primary_onset,
            second_view, threshold,
        )
        accepted.append(RivalHypothesis(
            rank=len(accepted) + 1,
            params={"entry_speed_kmh": round(speed, 3), "deceleration_ms2": round(decel, 3), "braking_onset_s": round(onset, 4)},
            residual=round(residual, 6),
            primary_residual=round(primary_residual, 6),
            materially_different=True,
            distinguishing_evidence=distinguishing,
            disambiguation_status=status,
            rejection_reason=reason,
        ))

    manifest_data = {
        "primary_run_id": primary_run.get("run_id", ""), "seed": seed,
        "bounds": bounds, "grid_n_per_dimension": n_grid,
        "threshold_m": threshold, "search_version": SEARCH_VERSION,
        "second_view": second_view,
        "primary_observation_hash": primary_obs_hash,
        "second_view_observation_hash": second_obs_hash,
    }
    search_id = hashlib.sha256(json.dumps(manifest_data, sort_keys=True).encode()).hexdigest()[:36]
    manifest = RivalManifest(
        search_id=search_id,
        primary_run_id=primary_run.get("run_id", ""),
        dimensions_searched=list(bounds),
        bounds=bounds,
        strategy=f"uniform_grid_{n_grid}^3",
        seed=seed,
        objective="2d ground-plane position RMSE in metres",
        acceptance_threshold=threshold,
        n_candidates_evaluated=evaluated,
        primary_observation_hash=primary_obs_hash,
        second_view_observation_hash=second_obs_hash,
    )
    empty = ""
    if not accepted:
        empty = (
            f"No acceptable materially different rival found in searched bounds; "
            f"speed={bounds['entry_speed_kmh']}, deceleration={bounds['deceleration_ms2']}, "
            f"onset={bounds['braking_onset_s']}, threshold={threshold:.3f} m, "
            f"strategy=uniform_grid_{n_grid}^3, seed={seed}. This does not rule out alternatives outside this search."
        )
    return RivalSearchResult(
        manifest=manifest,
        rivals=accepted,
        empty_search_message=empty,
        second_view_used=bool(second_view and _second_view_adequate(second_view)),
        second_view_notes=_second_view_notes(second_view),
    )


def _compute_residual(
    speed_kmh: float,
    decel_ms2: float,
    onset_s: float,
    observations: list[dict],
    direction: tuple[float, float] | None = None,
    origin: tuple[float, float] | None = None,
) -> float:
    obs = sorted(observations, key=lambda item: item["presentation_ts_s"])
    t = np.asarray([item["presentation_ts_s"] for item in obs], dtype=float)
    x = np.asarray([item["world_x_m"] for item in obs], dtype=float)
    y = np.asarray([item["world_y_m"] for item in obs], dtype=float)
    if direction is None:
        displacement = np.array([x[-1] - x[0], y[-1] - y[0]])
        norm = float(np.linalg.norm(displacement))
        if norm <= 1e-9:
            return math.inf
        direction_v = displacement / norm
    else:
        direction_v = np.asarray(direction, dtype=float)
        norm = float(np.linalg.norm(direction_v))
        if norm <= 1e-9:
            return math.inf
        direction_v /= norm
    origin_v = np.asarray(origin if origin is not None else (x[0], y[0]), dtype=float)
    dt = np.maximum(0.0, t - t[0])
    braking_delay = max(0.0, onset_s - t[0])
    v0 = speed_kmh / 3.6
    brake_elapsed = np.maximum(0.0, dt - braking_delay)
    brake_elapsed = np.minimum(brake_elapsed, v0 / max(decel_ms2, 1e-6))
    distance = v0 * np.minimum(dt, braking_delay) + v0 * brake_elapsed - 0.5 * decel_ms2 * brake_elapsed**2
    pred = origin_v + distance[:, None] * direction_v[None, :]
    return float(np.sqrt(np.mean(np.sum((pred - np.column_stack([x, y]))**2, axis=1))))


def _second_view_adequate(second_view: dict | None) -> bool:
    return bool(second_view and second_view.get("synchronized") is True
                and second_view.get("calibrated") is True
                and second_view.get("same_world_frame") is True
                and len(second_view.get("observations", [])) >= 5)


def _disambiguate(speed, decel, onset, primary_speed, primary_decel, primary_onset, second_view, threshold):
    evidence = "A synchronized, calibrated second view in the same world coordinate frame may distinguish this rival."
    if not second_view:
        return "unresolved", None, evidence
    if not _second_view_adequate(second_view):
        return "unresolved", "Second view lacks verified synchronization, calibration, shared world frame, or five timestamped observations.", None
    obs = second_view["observations"]
    # The shared world frame is essential: derive heading and origin from the
    # primary-view observations, then score both candidate histories against
    # second-view points using that same physical direction and coordinate frame.
    primary_obs = second_view.get("primary_observations")
    if not primary_obs or len(primary_obs) < 5:
        return "unresolved", "Second view cannot be scored without primary-view observations for shared heading/origin.", None
    ordered_primary = sorted(primary_obs, key=lambda item: item["presentation_ts_s"])
    dx = ordered_primary[-1]["world_x_m"] - ordered_primary[0]["world_x_m"]
    dy = ordered_primary[-1]["world_y_m"] - ordered_primary[0]["world_y_m"]
    norm = math.hypot(dx, dy)
    if norm <= 1e-9:
        return "unresolved", "Primary observations do not define a stable direction for shared-frame scoring.", None
    direction = (dx / norm, dy / norm)
    origin = (ordered_primary[0]["world_x_m"], ordered_primary[0]["world_y_m"])
    rival_res = _compute_residual(speed, decel, onset, obs, direction, origin)
    primary_res = _compute_residual(primary_speed, primary_decel, primary_onset, obs, direction, origin)
    if rival_res > threshold and primary_res <= threshold:
        return "rejected_by_evidence", f"Second-view residual for rival is {rival_res:.3f} m (> {threshold:.3f} m); primary is {primary_res:.3f} m (≤ threshold).", None
    return "unresolved", f"Second view did not cross the predeclared rejection threshold (rival={rival_res:.3f} m, primary={primary_res:.3f} m).", None


def _second_view_notes(second_view: dict | None) -> str:
    if second_view is None:
        return "No second view provided; all alternatives remain unresolved."
    if not _second_view_adequate(second_view):
        return "Second view is inadequate; it was not used to reject rivals."
    return "Caller supplied synchronization/calibration/shared-frame flags; they are not independently verified by this service. See each residual for the bounded comparison."

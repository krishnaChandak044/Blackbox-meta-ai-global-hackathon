"""Bounded, deterministic counterfactual simulation (always illustrative)."""

from __future__ import annotations

import json
import math
from typing import Any

from engine.dynamics.models import (
    CounterfactualIntervention,
    CounterfactualResult,
    DynamicsResult,
    FittedPoint,
    SensitivityEntry,
)


def run_counterfactual(
    baseline: DynamicsResult,
    intervention: CounterfactualIntervention,
    params: dict[str, Any] | None = None,
) -> CounterfactualResult:
    """Apply declared changes to a selected baseline; never changes baseline data."""
    params = params or {}
    if not baseline.fitted_points:
        raise ValueError("Baseline has no fitted trajectory")

    speed = intervention.entry_speed_override_kmh
    if speed is None:
        speed = baseline.entry_speed_kmh
    decel = intervention.decel_override_ms2
    if decel is None:
        decel = baseline.mean_decel_ms2
    if speed is None or speed <= 0:
        raise ValueError("Entry speed is not identifiable; provide an explicit scenario value")
    if decel is None or decel <= 0:
        raise ValueError("Deceleration is not identifiable; provide an explicit scenario value")

    max_shift = float(params.get("max_onset_shift_s", 2.0))
    min_speed = float(params.get("min_entry_speed_kmh", 0.0))
    max_speed = float(params.get("max_entry_speed_kmh", 200.0))
    min_decel = float(params.get("min_decel_ms2", 0.1))
    max_decel = float(params.get("max_decel_ms2", 15.0))
    has_observed_onset = baseline.braking_onset is not None
    outside = (
        abs(intervention.braking_onset_shift_s) > max_shift
        or not min_speed <= speed <= max_speed
        or not min_decel <= decel <= max_decel
        or not has_observed_onset
    )

    first = baseline.fitted_points[0]
    last = baseline.fitted_points[-1]
    start_t = first.presentation_ts_s
    brake_base = baseline.braking_onset.ts_lo_s if baseline.braking_onset else start_t
    brake_t = brake_base + intervention.braking_onset_shift_s
    speed_ms = speed / 3.6
    heading = math.atan2(first.vy_ms, first.vx_ms)
    direction_x, direction_y = math.cos(heading), math.sin(heading)
    delay = max(0.0, brake_t - start_t)
    stop_after_brake = speed_ms / decel
    stopping_distance = speed_ms * delay + speed_ms * speed_ms / (2.0 * decel)
    stopping_time = delay + stop_after_brake
    if stopping_time + start_t > last.presentation_ts_s:
        outside = True

    points: list[FittedPoint] = []
    for observed in baseline.fitted_points:
        elapsed = max(0.0, observed.presentation_ts_s - start_t)
        pre_brake = min(elapsed, delay)
        braking_elapsed = max(0.0, elapsed - delay)
        braking_elapsed = min(braking_elapsed, stop_after_brake)
        distance = speed_ms * pre_brake + speed_ms * braking_elapsed - 0.5 * decel * braking_elapsed**2
        current_speed = speed_ms if elapsed <= delay else max(0.0, speed_ms - decel * braking_elapsed)
        vx, vy = current_speed * direction_x, current_speed * direction_y
        points.append(FittedPoint(
            frame_index=observed.frame_index,
            presentation_ts_s=observed.presentation_ts_s,
            world_x_m=first.world_x_m + direction_x * distance,
            world_y_m=first.world_y_m + direction_y * distance,
            vx_ms=vx,
            vy_ms=vy,
            speed_ms=current_speed,
            speed_kmh=current_speed * 3.6,
            pos_sigma_x_m=observed.pos_sigma_x_m,
            pos_sigma_y_m=observed.pos_sigma_y_m,
            speed_lo_kmh=current_speed * 3.6,
            speed_hi_kmh=current_speed * 3.6,
        ))

    assumptions = {
        "motion_model": "constant_speed_then_constant_deceleration",
        "road_plane": "calibrated baseline coordinate plane",
        "steering": "ignored; heading fixed to initial fitted velocity",
        "friction": "not modeled; deceleration is an explicit scenario parameter",
        "interval_type": "single illustrative scenario, not a probability interval",
        "observed_time_range_s": [start_t, last.presentation_ts_s],
        "scenario_stopping_time_s_after_start": stopping_time,
        "braking_onset_basis": "detected interval" if has_observed_onset else "track start proxy; onset not identifiable",
        "intervention": {
            "braking_onset_shift_s": intervention.braking_onset_shift_s,
            "entry_speed_override_kmh": intervention.entry_speed_override_kmh,
            "decel_override_ms2": intervention.decel_override_ms2,
        },
    }
    return CounterfactualResult(
        baseline_run_id=baseline.run_id,
        intervention=intervention,
        simulated_points=points,
        stopping_distance_m=stopping_distance,
        stopping_time_s=stopping_time,
        extrapolation_outside_support=outside,
        assumptions_json=json.dumps(assumptions, sort_keys=True),
    )


def compute_sensitivity(
    baseline: DynamicsResult,
    perturbations: dict[str, list[float]] | None = None,
) -> list[SensitivityEntry]:
    """Finite-difference scenario sensitivity under explicit, bounded perturbations."""
    if baseline.entry_speed_kmh is None or baseline.mean_decel_ms2 is None:
        return []
    perturbations = perturbations or {
        "entry_speed_override_kmh": [max(0.0, baseline.entry_speed_kmh - 5), baseline.entry_speed_kmh + 5],
        "braking_onset_shift_s": [-0.5, 0.5],
        "decel_override_ms2": [max(0.1, baseline.mean_decel_ms2 - 1), baseline.mean_decel_ms2 + 1],
    }
    base = run_counterfactual(baseline, CounterfactualIntervention()).stopping_distance_m or 0.0
    specs = {
        "entry_speed_override_kmh": ("km/h", "Independent calibrated speed observation"),
        "braking_onset_shift_s": ("s", "Higher-frame-rate video spanning onset"),
        "decel_override_ms2": ("m/s²", "Scene-specific deceleration/friction measurement"),
    }
    output: list[SensitivityEntry] = []
    for name, values in perturbations.items():
        if name not in specs or not values:
            continue
        deltas = []
        for value in values:
            intervention = CounterfactualIntervention(**{name: value})
            result = run_counterfactual(baseline, intervention)
            deltas.append((value, (result.stopping_distance_m or 0.0) - base))
        value, delta = max(deltas, key=lambda item: abs(item[1]))
        unit, evidence = specs[name]
        output.append(SensitivityEntry(name, value, unit, float(delta), evidence))
    return sorted(output, key=lambda item: abs(item.stopping_distance_delta_m), reverse=True)

"""G5 Physics Recovery Benchmark Suite.

Evaluates physics recovery, speed interval containment, and refusal behavior
across diverse held-out synthetic scenarios (constant speeds, moderate/hard braking,
sensor noise, frame dropouts, and uncalibrated inputs).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from engine.dynamics.inference import InferenceRejected, run_inference
from engine.dynamics.models import DynamicsResult


DEFAULT_CALIBRATION: dict[str, Any] = {
    "metres_per_pixel": 0.05,
    "homography_rmse_px": 0.5,
    "scale_relative_error": 0.002,
    "homography_fit_id": "g5-synthetic-calibration-v1",
}

DEFAULT_VFR: dict[str, Any] = {
    "has_vfr": False,
    "pts_available": True,
    "mean_frame_duration_s": 0.04,
    "frame_duration_sigma_s": 0.000001,
    "model_speed_bound_ms": 0.05,
    "timestamp_metadata": "g5-synthetic-monotonic-pts",
}

DEFAULT_PARAMS: dict[str, Any] = {
    "bounds": {
        "max_speed_ms": 60.0,
        "max_accel_ms2": 20.0,
    },
    "try_two_segment": True,
}


@dataclass(frozen=True)
class G5ScenarioSpec:
    """Specification for a G5 synthetic evaluation scenario."""
    name: str
    description: str
    speed_kmh: float | None
    decel_ms2: float | None
    braking_onset_s: float
    duration_s: float
    fps: int
    noise_px: float
    missing_frame_rate: float
    seed: int
    expect_abstain: bool = False


@dataclass
class G5ScenarioResult:
    """Evaluation result for a single scenario."""
    spec: G5ScenarioSpec
    passed: bool
    converged: bool
    abstain_correct: bool = False
    true_speed_kmh: float | None = None
    estimated_speed_kmh: float | None = None
    speed_lo_kmh: float | None = None
    speed_hi_kmh: float | None = None
    speed_error_kmh: float | None = None
    relative_error_pct: float | None = None
    interval_contains_truth: bool | None = None
    rmse_metres: float | None = None
    chi2_reduced: float | None = None
    notes: str = ""


# Pre-declared held-out evaluation scenarios
G5_SCENARIOS: list[G5ScenarioSpec] = [
    G5ScenarioSpec(
        name="constant_slow",
        description="Low-speed steady motion (20 km/h) under sub-pixel sensor noise",
        speed_kmh=20.0,
        decel_ms2=0.0,
        braking_onset_s=999.0,
        duration_s=2.5,
        fps=25,
        noise_px=0.5,
        missing_frame_rate=0.00,
        seed=42,
    ),
    G5ScenarioSpec(
        name="constant_fast",
        description="Highway-speed steady motion (80 km/h) with 1px sensor jitter",
        speed_kmh=80.0,
        decel_ms2=0.0,
        braking_onset_s=999.0,
        duration_s=2.0,
        fps=25,
        noise_px=1.0,
        missing_frame_rate=0.00,
        seed=43,
    ),
    G5ScenarioSpec(
        name="moderate_braking",
        description="Urban braking from 50 km/h at 4.0 m/s2 with 5% sporadic frame drops",
        speed_kmh=50.0,
        decel_ms2=4.0,
        braking_onset_s=1.0,
        duration_s=2.5,
        fps=25,
        noise_px=0.8,
        missing_frame_rate=0.05,
        seed=44,
    ),
    G5ScenarioSpec(
        name="hard_braking",
        description="Emergency stop from 60 km/h at 8.0 m/s2 under 1.5px noise and 10% drop",
        speed_kmh=60.0,
        decel_ms2=8.0,
        braking_onset_s=0.8,
        duration_s=2.5,
        fps=25,
        noise_px=1.5,
        missing_frame_rate=0.10,
        seed=45,
    ),
    G5ScenarioSpec(
        name="noisy_sparse",
        description="Low speed (35 km/h) with severe noise (3px) and 25% dropped frames",
        speed_kmh=35.0,
        decel_ms2=3.0,
        braking_onset_s=0.9,
        duration_s=2.5,
        fps=25,
        noise_px=3.0,
        missing_frame_rate=0.25,
        seed=46,
    ),
    G5ScenarioSpec(
        name="severe_decel_high_speed",
        description="High speed (90 km/h) with sharp deceleration (9.0 m/s2) and 15% drop",
        speed_kmh=90.0,
        decel_ms2=9.0,
        braking_onset_s=1.0,
        duration_s=2.5,
        fps=25,
        noise_px=2.0,
        missing_frame_rate=0.15,
        seed=48,
    ),
    G5ScenarioSpec(
        name="uncalibrated_refusal",
        description="Uncalibrated footage; system must explicitly abstain from metric speeds",
        speed_kmh=None,
        decel_ms2=None,
        braking_onset_s=0.0,
        duration_s=2.0,
        fps=25,
        noise_px=0.0,
        missing_frame_rate=0.00,
        seed=47,
        expect_abstain=True,
    ),
]


def generate_synthetic_track(spec: G5ScenarioSpec, m_per_px: float = 0.05) -> list[dict[str, Any]]:
    """Synthesizes physical 1D trajectory projected to ground coordinates with noise."""
    if spec.expect_abstain:
        return []

    rng = np.random.default_rng(spec.seed)
    total_frames = int(spec.duration_s * spec.fps)
    times = np.linspace(0.0, spec.duration_s, total_frames)
    v0 = (spec.speed_kmh or 0.0) / 3.6
    decel = spec.decel_ms2 or 0.0
    onset = spec.braking_onset_s
    noise_sigma_m = spec.noise_px * m_per_px

    obs: list[dict[str, Any]] = []
    for i, ts in enumerate(times):
        # Drop frames according to missing_frame_rate, keeping first/last 5 intact
        if spec.missing_frame_rate > 0.0 and (5 < i < total_frames - 5):
            if rng.random() < spec.missing_frame_rate:
                continue

        if ts <= onset or decel <= 0.0:
            dist = v0 * ts
        else:
            dt = ts - onset
            dt_stop = v0 / max(decel, 1e-6)
            braking_dt = min(dt, dt_stop)
            dist = v0 * onset + v0 * braking_dt - 0.5 * decel * braking_dt**2

        noise_x = rng.normal(0.0, max(noise_sigma_m, 1e-4))
        noise_y = rng.normal(0.0, max(noise_sigma_m, 1e-4))

        obs.append({
            "frame_index": i,
            "presentation_ts_s": float(ts),
            "world_x_m": float(dist + noise_x),
            "world_y_m": float(noise_y),
            "localisation_sigma_m": float(max(noise_sigma_m, 0.01)),
        })
    return obs


def evaluate_scenario(spec: G5ScenarioSpec) -> G5ScenarioResult:
    """Runs dynamics inference and evaluates interval coverage and error."""
    if spec.expect_abstain:
        try:
            run_inference(
                observations=[],
                calibration={},  # uncalibrated
                vfr_meta=DEFAULT_VFR,
                params=DEFAULT_PARAMS,
                track_id=f"g5_{spec.name}",
                track_version_hash="v1",
                media_sha256="synth",
                software_revision="rev1",
                seed=spec.seed,
            )
            return G5ScenarioResult(
                spec=spec,
                passed=False,
                converged=False,
                abstain_correct=False,
                notes="FAILED: Inference ran when it should have raised InferenceRejected.",
            )
        except InferenceRejected as err:
            return G5ScenarioResult(
                spec=spec,
                passed=True,
                converged=True,
                abstain_correct=True,
                notes=f"PASSED: Correctly refused speed estimation ({err})",
            )

    observations = generate_synthetic_track(spec)
    try:
        result: DynamicsResult = run_inference(
            observations=observations,
            calibration=DEFAULT_CALIBRATION,
            vfr_meta=DEFAULT_VFR,
            params=DEFAULT_PARAMS,
            track_id=f"g5_{spec.name}",
            track_version_hash="v1",
            media_sha256="synth",
            software_revision="rev1",
            seed=spec.seed,
        )
    except Exception as exc:
        return G5ScenarioResult(
            spec=spec,
            passed=False,
            converged=False,
            notes=f"Execution error: {exc}",
        )

    truth = spec.speed_kmh or 0.0
    est = result.entry_speed_kmh or 0.0
    lo = result.entry_speed_lo_kmh or 0.0
    hi = result.entry_speed_hi_kmh or 0.0
    err = abs(est - truth)
    rel_err = (err / truth) * 100.0 if truth > 0 else 0.0
    inside = (lo <= truth <= hi)
    converged = bool(result.fit_quality.converged)

    # Acceptance criterion: converged, truth inside interval, and error < 5.0 km/h
    passed = converged and inside and (err < 5.0)

    return G5ScenarioResult(
        spec=spec,
        passed=passed,
        converged=converged,
        true_speed_kmh=round(truth, 3),
        estimated_speed_kmh=round(est, 3),
        speed_lo_kmh=round(lo, 3),
        speed_hi_kmh=round(hi, 3),
        speed_error_kmh=round(err, 4),
        relative_error_pct=round(rel_err, 2),
        interval_contains_truth=inside,
        rmse_metres=round(result.fit_quality.rmse_metres, 4),
        chi2_reduced=round(result.fit_quality.reduced_chi_squared, 4),
        notes="PASS" if passed else "FAIL",
    )


def run_g5_suite(scenarios: list[G5ScenarioSpec] | None = None) -> dict[str, Any]:
    """Runs all G5 scenarios and compiles statistical coverage report."""
    specs = scenarios or G5_SCENARIOS
    results = [evaluate_scenario(spec) for spec in specs]

    measurable = [r for r in results if not r.spec.expect_abstain]
    abstain = [r for r in results if r.spec.expect_abstain]

    coverage_count = sum(1 for r in measurable if r.interval_contains_truth)
    coverage_rate = (coverage_count / len(measurable)) if measurable else 1.0
    all_passed = all(r.passed for r in results)

    errors = [r.speed_error_kmh for r in measurable if r.speed_error_kmh is not None]
    biases = [
        (r.estimated_speed_kmh - r.true_speed_kmh)
        for r in measurable
        if r.estimated_speed_kmh is not None and r.true_speed_kmh is not None
    ]
    rmses = [r.rmse_metres for r in measurable if r.rmse_metres is not None]

    mean_bias = float(np.mean(biases)) if biases else 0.0
    mean_abs_error = float(np.mean(errors)) if errors else 0.0
    max_abs_error = float(np.max(errors)) if errors else 0.0
    mean_track_rmse = float(np.mean(rmses)) if rmses else 0.0

    overall_status = "PASS" if (all_passed and coverage_rate >= 0.80) else "FAIL"

    return {
        "gate": "G5-physics-recovery-coverage",
        "status": overall_status,
        "n_scenarios_evaluated": len(results),
        "n_measurable_scenarios": len(measurable),
        "n_refusal_scenarios": len(abstain),
        "empirical_interval_coverage_pct": round(coverage_rate * 100.0, 1),
        "coverage_threshold_pct": 80.0,
        "mean_bias_kmh": round(mean_bias, 4),
        "mean_absolute_error_kmh": round(mean_abs_error, 4),
        "max_absolute_error_kmh": round(max_abs_error, 4),
        "mean_track_fit_rmse_m": round(mean_track_rmse, 4),
        "all_refusals_correct": all(r.abstain_correct for r in abstain),
        "results": results,
    }


if __name__ == "__main__":
    summary = run_g5_suite()
    print(f"G5 Suite Status: {summary['status']}")
    print(f"Coverage: {summary['empirical_interval_coverage_pct']}% (Threshold: 80%)")
    print(f"Mean Abs Error: {summary['mean_absolute_error_kmh']} km/h")
    print(f"Max Abs Error:  {summary['max_absolute_error_kmh']} km/h")
    for r in summary["results"]:
        if r.spec.expect_abstain:
            print(f"  {r.spec.name:25s} -> Abstain correct: {r.abstain_correct}")
        else:
            print(
                f"  {r.spec.name:25s} -> Truth: {r.true_speed_kmh:4.1f} km/h | "
                f"Est: {r.estimated_speed_kmh:5.2f} [{r.speed_lo_kmh:5.2f}, {r.speed_hi_kmh:5.2f}] | "
                f"Err: {r.speed_error_kmh:.3f} km/h | Covered: {r.interval_contains_truth}"
            )


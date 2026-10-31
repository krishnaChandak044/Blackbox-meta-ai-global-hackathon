"""Deterministic acceptance fixtures for Phase 4 dynamics and G5/G6."""

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pytest

from engine.dynamics.inference import InferenceRejected, run_inference


CALIBRATION = {
    "metres_per_pixel": 0.05,
    "homography_rmse_px": 0.5,
    "scale_relative_error": 0.002,
    "homography_fit_id": "synthetic-calibration",
}
VFR = {
    "has_vfr": False,
    "pts_available": True,
    "mean_frame_duration_s": 0.1,
    "frame_duration_sigma_s": 0.000001,
    "model_speed_bound_ms": 0.05,
    "timestamp_metadata": "synthetic exact timestamps",
}
PARAMS = {"bounds": {"max_speed_ms": 50.0, "max_accel_ms2": 15.0}, "try_two_segment": False}


def _constant_speed_observations(noise_sigma: float = 0.0002) -> tuple[list[dict], float]:
    rng = np.random.default_rng(8675309)
    times = np.arange(0.0, 2.01, 0.1)
    true_speed = 12.0
    observations = []
    for index, time_s in enumerate(times):
        observations.append({
            "frame_index": index,
            "presentation_ts_s": float(time_s),
            "world_x_m": float(true_speed * time_s + rng.normal(0, noise_sigma)),
            "world_y_m": float(rng.normal(0, noise_sigma)),
            "localisation_sigma_m": noise_sigma,
        })
    return observations, true_speed


def _run(observations: list[dict], seed: int = 17):
    return run_inference(
        observations=observations,
        calibration=CALIBRATION,
        vfr_meta=VFR,
        params=PARAMS,
        track_id="synthetic-track",
        track_version_hash="synthetic-track-hash",
        media_sha256="synthetic-media-hash",
        software_revision="synthetic-revision",
        seed=seed,
    )


def test_g5_synthetic_known_speed_is_recovered_within_interval():
    observations, truth_speed = _constant_speed_observations()
    result = _run(observations)

    assert result.fit_quality.converged
    assert result.entry_speed_lo_kmh is not None
    assert result.entry_speed_hi_kmh is not None
    assert result.entry_speed_lo_kmh <= truth_speed * 3.6 <= result.entry_speed_hi_kmh
    assert abs(result.entry_speed_kmh - truth_speed * 3.6) < 0.2
    assert result.interval_type == "illustrative_range"


def test_g5_uncalibrated_input_is_rejected_instead_of_estimating_speed():
    observations, _ = _constant_speed_observations()
    with pytest.raises(InferenceRejected, match="calibration_invalid"):
        run_inference(
            observations=observations,
            calibration={"metres_per_pixel": None},
            vfr_meta=VFR,
            params=PARAMS,
            track_id="synthetic-track",
            track_version_hash="synthetic-track-hash",
            media_sha256="synthetic-media-hash",
            software_revision="synthetic-revision",
            seed=17,
        )


def test_g6_same_inputs_and_seed_serialize_identically():
    observations, _ = _constant_speed_observations()
    first = _run(observations, seed=321)
    second = _run(observations, seed=321)

    assert json.dumps(asdict(first), sort_keys=True) == json.dumps(asdict(second), sort_keys=True)
    assert first.run_id == second.run_id

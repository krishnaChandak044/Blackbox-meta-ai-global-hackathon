"""G6 reproducibility and G8 planted-rival acceptance cases."""

from __future__ import annotations

import numpy as np

from engine.rival.hypothesis_search import _compute_residual, search_rivals


def _track(speed_kmh: float, decel_ms2: float, onset_s: float, *,
           start_s: float = 0.0, end_s: float = 2.0, count: int = 21,
           origin=(0.0, 0.0)) -> list[dict]:
    times = np.linspace(start_s, end_s, count)
    speed_ms = speed_kmh / 3.6
    delay = max(0.0, onset_s - start_s)
    points = []
    for frame, time_s in enumerate(times):
        elapsed = time_s - start_s
        braking_elapsed = max(0.0, elapsed - delay)
        braking_elapsed = min(braking_elapsed, speed_ms / decel_ms2)
        distance = speed_ms * min(elapsed, delay) + speed_ms * braking_elapsed - 0.5 * decel_ms2 * braking_elapsed**2
        points.append({
            "frame_index": frame,
            "presentation_ts_s": float(time_s),
            "world_x_m": float(origin[0] + distance),
            "world_y_m": float(origin[1]),
        })
    return points


def test_g6_rival_search_is_reproducible_for_same_seed_and_inputs():
    observations = _track(54.0, 6.0, 1.0)
    primary = {"run_id": "primary", "entry_speed_kmh": 54.0,
               "mean_decel_ms2": 6.0, "braking_onset_s": 1.0}
    options = {"n_grid": 9, "acceptance_threshold_m": 0.75}

    first = search_rivals(primary, observations, {"calibrated": True}, options, seed=99)
    second = search_rivals(primary, observations, {"calibrated": True}, options, seed=99)

    assert first == second
    assert first.manifest.search_id == second.manifest.search_id


def test_g8_planted_rival_found_on_one_view_and_rejected_by_second_view():
    primary_params = {"entry_speed_kmh": 54.0, "deceleration_ms2": 6.0, "braking_onset_s": 1.0}
    primary_observations = _track(**{
        "speed_kmh": primary_params["entry_speed_kmh"],
        "decel_ms2": primary_params["deceleration_ms2"],
        "onset_s": primary_params["braking_onset_s"],
    }, end_s=3.0, count=31)
    # Camera A only sees a short pre-braking interval, so nearby speeds remain
    # within the predeclared residual tolerance.
    single_view = primary_observations[:6]
    base_options = {
        "n_grid": 21,
        "acceptance_threshold_m": 1.5,
        "speed_lo_kmh": 40.0,
        "speed_hi_kmh": 80.0,
        "decel_lo_ms2": 2.0,
        "decel_hi_ms2": 10.0,
        "onset_lo_s": 0.7,
        "onset_hi_s": 1.4,
    }
    # Make one specific planted rival the primary comparison: 54 km/h is the
    # actual hidden speed; a 60 km/h alternative has only 0.505 m RMSE on the
    # short crop, under the predeclared 1.5 m tolerance. The full view separates it.
    ambiguous_primary = {"run_id": "primary", "entry_speed_kmh": 60.0,
                         "mean_decel_ms2": 6.0, "braking_onset_s": 1.0}
    one_view_primary_res = _compute_residual(60.0, 6.0, 1.0, single_view)
    one_view_rival_res = _compute_residual(54.0, 6.0, 1.0, single_view)
    assert one_view_rival_res <= one_view_primary_res + base_options["acceptance_threshold_m"]
    assert one_view_primary_res < base_options["acceptance_threshold_m"]
    # Camera B observes the same interval in the same calibrated world frame.
    # The high-speed rival predicts a larger displacement and must cross the
    # predeclared residual threshold while the primary stays within it.
    second_view_observations = _track(54.0, 6.0, 1.0, start_s=0.0, end_s=3.0, count=31)
    with_second_view = search_rivals(
        ambiguous_primary,
        single_view,
        {"calibrated": True},
        base_options,
        second_view={
            "synchronized": True,
            "calibrated": True,
            "same_world_frame": True,
            "observations": second_view_observations,
            "primary_observations": primary_observations,
        },
        seed=7,
    )
    direction = (1.0, 0.0)
    origin = (0.0, 0.0)
    two_view_primary_res = _compute_residual(60.0, 6.0, 1.0, second_view_observations, direction, origin)
    two_view_rival_res = _compute_residual(54.0, 6.0, 1.0, second_view_observations, direction, origin)
    assert two_view_primary_res > base_options["acceptance_threshold_m"]
    assert two_view_rival_res <= base_options["acceptance_threshold_m"]

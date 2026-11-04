"""G8 Rival Hypothesis Search Suite.

Evaluates:
1. Scenario 1 (Planted Ambiguity + Disambiguation):
   Single view has speed ambiguity; synchronized, calibrated, shared-world-frame
   second view rejects the rival while supporting the primary.
2. Scenario 2 (No Rival Found / Clean Search Refusal):
   Unambiguous track where no alternative kinematic history fits within tolerance;
   system articulates search limits and reports empty results without hallucinating.
3. Scenario 3 (Inadequate Second View / Honest Unresolved Fallback):
   Camera B lacks verified synchronization, calibration, shared frame, or sufficient points;
   rival remains 'unresolved' and why the second view was unusable is disclosed.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from engine.rival.hypothesis_search import _compute_residual, search_rivals


def _generate_synthetic_track(
    speed_kmh: float,
    decel_ms2: float,
    onset_s: float,
    *,
    start_s: float = 0.0,
    end_s: float = 3.0,
    count: int = 31,
    origin: tuple[float, float] = (0.0, 0.0),
) -> list[dict[str, Any]]:
    times = np.linspace(start_s, end_s, count)
    speed_ms = speed_kmh / 3.6
    delay = max(0.0, onset_s - start_s)
    points: list[dict[str, Any]] = []
    for frame, time_s in enumerate(times):
        elapsed = time_s - start_s
        braking_elapsed = max(0.0, elapsed - delay)
        braking_elapsed = min(braking_elapsed, speed_ms / max(decel_ms2, 1e-6))
        distance = (
            speed_ms * min(elapsed, delay)
            + speed_ms * braking_elapsed
            - 0.5 * decel_ms2 * braking_elapsed**2
        )
        points.append({
            "frame_index": frame,
            "presentation_ts_s": float(time_s),
            "world_x_m": float(origin[0] + distance),
            "world_y_m": float(origin[1]),
        })
    return points


def evaluate_scenario_1_planted_disambiguation() -> dict[str, Any]:
    """Scenario 1: Planted rival disambiguated by calibrated shared-frame second view."""
    # The true physical trajectory has entry speed 54 km/h with 6.0 m/s2 braking onset at 1.0s
    primary_params = {
        "run_id": "primary_true",
        "entry_speed_kmh": 54.0,
        "mean_decel_ms2": 6.0,
        "braking_onset_s": 1.0,
    }
    full_track = _generate_synthetic_track(
        speed_kmh=54.0,
        decel_ms2=6.0,
        onset_s=1.0,
        end_s=3.0,
        count=31,
    )
    # Camera A only sees 6 frames before braking — short crop produces ambiguity
    single_view = full_track[:6]

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

    # Verify single view allows alternative candidates under the 1.5m tolerance
    v1_prim_res = _compute_residual(54.0, 6.0, 1.0, single_view)
    v1_alt_res = _compute_residual(60.0, 6.0, 1.0, single_view)
    single_view_ambiguous = (
        v1_prim_res <= base_options["acceptance_threshold_m"]
        and v1_alt_res <= base_options["acceptance_threshold_m"]
    )

    # Second view provides full sequence in shared world frame
    result = search_rivals(
        primary_run=primary_params,
        observations=single_view,
        calibration={"calibrated": True},
        params=base_options,
        second_view={
            "synchronized": True,
            "calibrated": True,
            "same_world_frame": True,
            "observations": full_track,
            "primary_observations": full_track,
        },
        seed=7,
    )

    has_rivals = len(result.rivals) > 0
    rejected_rivals = [r for r in result.rivals if r.disambiguation_status == "rejected_by_evidence"]
    has_rejected = len(rejected_rivals) > 0
    top_rejected = rejected_rivals[0] if has_rejected else None
    reason_has_residuals = bool(top_rejected and "Second-view residual" in (top_rejected.rejection_reason or ""))

    passed = single_view_ambiguous and has_rivals and has_rejected and reason_has_residuals
    return {
        "scenario": "planted_disambiguation",
        "passed": passed,
        "single_view_ambiguous": single_view_ambiguous,
        "rival_count": len(result.rivals),
        "rejected_count": len(rejected_rivals),
        "top_rejected_params": top_rejected.params if top_rejected else None,
        "top_rejection_reason": top_rejected.rejection_reason if top_rejected else None,
        "second_view_used": result.second_view_used,
    }


def evaluate_scenario_2_no_rival_found() -> dict[str, Any]:
    """Scenario 2: Dense unambiguous track where no rival exists within bounds."""
    full_track = _generate_synthetic_track(50.0, 4.0, 1.0, end_s=3.0, count=31)
    primary = {
        "run_id": "primary_unambiguous",
        "entry_speed_kmh": 50.0,
        "mean_decel_ms2": 4.0,
        "braking_onset_s": 1.0,
    }
    # Strict acceptance threshold where no alternative fits
    strict_options = {
        "n_grid": 11,
        "acceptance_threshold_m": 0.08,
        "speed_lo_kmh": 40.0,
        "speed_hi_kmh": 60.0,
        "decel_lo_ms2": 2.0,
        "decel_hi_ms2": 6.0,
    }
    result = search_rivals(
        primary_run=primary,
        observations=full_track,
        calibration={"calibrated": True},
        params=strict_options,
        seed=42,
    )

    no_rivals = (len(result.rivals) == 0)
    has_message = bool(result.empty_search_message and "No acceptable materially different rival" in result.empty_search_message)
    bounds_disclosed = bool("speed=" in result.empty_search_message and "threshold=" in result.empty_search_message)

    passed = no_rivals and has_message and bounds_disclosed
    return {
        "scenario": "no_rival_found",
        "passed": passed,
        "rival_count": len(result.rivals),
        "empty_search_message": result.empty_search_message,
        "candidates_evaluated": result.manifest.n_candidates_evaluated,
    }


def evaluate_scenario_3_inadequate_second_view() -> dict[str, Any]:
    """Scenario 3: Second view is inadequate; rivals must stay 'unresolved'."""
    full_track = _generate_synthetic_track(54.0, 6.0, 1.0, end_s=3.0, count=31)
    single_view = full_track[:6]
    ambiguous_primary = {
        "run_id": "primary_view_1",
        "entry_speed_kmh": 60.0,
        "mean_decel_ms2": 6.0,
        "braking_onset_s": 1.0,
    }
    options = {
        "n_grid": 15,
        "acceptance_threshold_m": 1.5,
        "speed_lo_kmh": 50.0,
        "speed_hi_kmh": 65.0,
    }

    # Case 3A: same_world_frame is False
    inadequate_frame = {
        "synchronized": True,
        "calibrated": True,
        "same_world_frame": False,  # Missing shared coordinate frame!
        "observations": full_track,
        "primary_observations": full_track,
    }
    res_a = search_rivals(ambiguous_primary, single_view, {"calibrated": True}, options, second_view=inadequate_frame, seed=11)

    # Case 3B: fewer than 5 observations in second view
    inadequate_obs = {
        "synchronized": True,
        "calibrated": True,
        "same_world_frame": True,
        "observations": full_track[:3],  # < 5 points!
        "primary_observations": full_track,
    }
    res_b = search_rivals(ambiguous_primary, single_view, {"calibrated": True}, options, second_view=inadequate_obs, seed=12)

    # Case 3C: calibrated is False
    inadequate_cal = {
        "synchronized": True,
        "calibrated": False,  # Uncalibrated!
        "same_world_frame": True,
        "observations": full_track,
        "primary_observations": full_track,
    }
    res_c = search_rivals(ambiguous_primary, single_view, {"calibrated": True}, options, second_view=inadequate_cal, seed=13)

    check_a = all(r.disambiguation_status == "unresolved" for r in res_a.rivals) and not res_a.second_view_used
    check_b = all(r.disambiguation_status == "unresolved" for r in res_b.rivals) and not res_b.second_view_used
    check_c = all(r.disambiguation_status == "unresolved" for r in res_c.rivals) and not res_c.second_view_used

    passed = check_a and check_b and check_c
    return {
        "scenario": "inadequate_second_view",
        "passed": passed,
        "case_3a_unshared_frame_unresolved": check_a,
        "case_3b_insufficient_points_unresolved": check_b,
        "case_3c_uncalibrated_unresolved": check_c,
        "sample_rejection_reason": res_a.rivals[0].rejection_reason if res_a.rivals else None,
        "sample_second_view_notes": res_a.second_view_notes,
    }


def run_g8_suite() -> dict[str, Any]:
    """Runs all three G8 rival search acceptance scenarios."""
    scenarios = [
        evaluate_scenario_1_planted_disambiguation(),
        evaluate_scenario_2_no_rival_found(),
        evaluate_scenario_3_inadequate_second_view(),
    ]
    all_passed = all(s["passed"] for s in scenarios)
    return {
        "gate": "G8-rival-discovery-and-refusal",
        "status": "PASS" if all_passed else "FAIL",
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    result = run_g8_suite()
    print(f"G8 Suite Status: {result['status']}")
    for s in result["scenarios"]:
        status_icon = "✅" if s["passed"] else "❌"
        print(f"  {status_icon} {s['scenario']}")

"""Pytest test suite for Phase 4 Gate Expansion (G5, G6, G8)."""
from __future__ import annotations

from pathlib import Path
import pytest

from evaluation.synthetic.g5_suite import G5_SCENARIOS, evaluate_scenario, run_g5_suite
from evaluation.runners.g6_reproducibility import run_g6_suite
from evaluation.runners.g8_rival_suite import (
    evaluate_scenario_1_planted_disambiguation,
    evaluate_scenario_2_no_rival_found,
    evaluate_scenario_3_inadequate_second_view,
    run_g8_suite,
)


# ---------------------------------------------------------------------------
# G5: Physics Recovery Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", G5_SCENARIOS, ids=lambda s: s.name)
def test_g5_held_out_scenario(scenario):
    """Each held-out scenario must either recover true speed inside interval or refuse uncalibrated."""
    res = evaluate_scenario(scenario)
    assert res.passed, f"Scenario {scenario.name} failed: {res.notes}"
    if scenario.expect_abstain:
        assert res.abstain_correct
    else:
        assert res.converged
        assert res.interval_contains_truth, (
            f"True speed {res.true_speed_kmh} km/h outside interval "
            f"[{res.speed_lo_kmh}, {res.speed_hi_kmh}]"
        )
        assert res.speed_error_kmh < 5.0


def test_g5_overall_suite_coverage():
    """G5 suite as a whole must achieve >= 80% coverage on held-out tracks."""
    summary = run_g5_suite()
    assert summary["status"] == "PASS"
    assert summary["empirical_interval_coverage_pct"] >= 80.0
    assert summary["all_refusals_correct"]


# ---------------------------------------------------------------------------
# G6: Cross-Process Determinism & Sensitivity Tests
# ---------------------------------------------------------------------------

def test_g6_cross_process_and_sensitivity_suite(tmp_path: Path):
    """G6 tests multi-process determinism and responsiveness to prior assumptions."""
    summary = run_g6_suite(temp_dir=tmp_path)
    assert summary["status"] == "PASS"
    for check in summary["checks"]:
        assert check["passed"], f"G6 check failed: {check['check']}"


# ---------------------------------------------------------------------------
# G8: Rival Hypothesis Search Tests
# ---------------------------------------------------------------------------

def test_g8_scenario_1_planted_disambiguation():
    res = evaluate_scenario_1_planted_disambiguation()
    assert res["passed"]
    assert res["single_view_ambiguous"]
    assert res["rejected_count"] > 0
    assert res["second_view_used"]


def test_g8_scenario_2_no_rival_found():
    res = evaluate_scenario_2_no_rival_found()
    assert res["passed"]
    assert res["rival_count"] == 0
    assert "No acceptable materially different rival" in res["empty_search_message"]


def test_g8_scenario_3_inadequate_second_view():
    res = evaluate_scenario_3_inadequate_second_view()
    assert res["passed"]
    assert res["case_3a_unshared_frame_unresolved"]
    assert res["case_3b_insufficient_points_unresolved"]
    assert res["case_3c_uncalibrated_unresolved"]


def test_g8_overall_suite():
    summary = run_g8_suite()
    assert summary["status"] == "PASS"

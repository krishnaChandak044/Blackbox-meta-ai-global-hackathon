# Phase 4 gate verification — 2026-10-31

## Scope

Focused synthetic verification of G5, G6, and G8. This report records implementation checks only. It is not a forensic validation study, and no confidence-coverage claim is made.

## Environment

- Python: 3.11
- NumPy: 2.4.6
- SciPy: 1.17.1
- pytest: 7.3.0
- Command: `pytest -q engine/tests/test_dynamics.py engine/tests/test_counterfactual.py`

## Results

| Gate | Result | Evidence |
| --- | --- | --- |
| G5 | PASS for a seeded synthetic constant-speed case; abstention on missing calibration also passes | `test_g5_synthetic_known_speed_is_recovered_within_interval` and `test_g5_uncalibrated_input_is_rejected_instead_of_estimating_speed`; truth 43.2 km/h, estimate 43.1995 km/h, illustrative range 41.1134–45.2857 km/h, 21 points, fit RMSE 0.000193 m |
| G6 | PASS for repeated same-runtime inference and rival search inputs/seeds | `test_g6_same_inputs_and_seed_serialize_identically` and `test_g6_rival_search_is_reproducible_for_same_seed_and_inputs` |
| G8 | PASS for a planted speed ambiguity in a bounded synthetic single-view/second-view comparison | `test_g8_planted_rival_found_on_one_view_and_rejected_by_second_view`; the 60 km/h primary versus 54 km/h planted alternative has 0.5046 m RMSE on a short crop; full second-view residuals are checked against the predeclared 1.5 m threshold in a shared coordinate frame |

Test result: **5 passed**. Pytest emitted two warnings because the locally installed pytest 7.3.0 does not recognize the repository's pytest-asyncio configuration options.

## Limitations and outstanding validation

- G5 is only a single deterministic constant-speed case plus an uncalibrated refusal case. It does not establish 90/95% interval coverage, performance across braking profiles, noisy/missing frames, or the five uncertainty sources. Intervals remain `illustrative_range`.
- G6 establishes repeatability on this local Python/NumPy/SciPy runtime. Cross-platform or cross-version bitwise determinism is not evaluated.
- G8 is an engine-level synthetic demonstration with caller-declared synchronization, calibration, and shared-frame metadata. The API does not independently verify those declarations; the result must not be described as real multi-camera forensic disambiguation.
- No real crash footage, human annotations, external instrumentation, or legal conclusions were used.

## Code fixes made while testing

- Corrected weighted least-squares residual construction so each x/y observation gets its own weight vector.
- Rival second-view scoring now requires primary-view observations and uses their shared heading/origin to score alternatives in the declared common world frame.
- Added a conservative fallback reference deceleration only for bounded rival-search bounds when the dynamics result lacks a deceleration value; the search manifest continues to disclose the bounds, and this reference is not itself reported as a measured deceleration.

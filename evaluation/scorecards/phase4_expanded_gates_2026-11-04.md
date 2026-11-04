# Phase 4 Gate Expansion Verification Scorecard — 2026-11-04

- **Suite:** Phase 4 Gate Expansion Suite (G5, G6, G8)
- **Overall Status:** **PASS**
- **Executed At (UTC):** `2026-11-04T05:08:44.319998+00:00`
- **Python Runtime:** `3.11.6` on `darwin`

---

## Executive Gate Summary

| Gate | Name | Result | Primary Metric / Evidence |
|---|---|---|---|
| **G5** | Physics Recovery Coverage | **PASS** | Coverage: 100.0% (Target ≥80%), Mean Error: 0.8912 km/h |
| **G6** | Cross-Process Reproducibility | **PASS** | Bit-exact cross-process hashes match; sensitivity responsiveness confirmed |
| **G8** | Rival Hypothesis Discovery | **PASS** | 3/3 scenarios PASS (planted disambiguation, empty refusal, inadequate fallback) |

---

## Gate G5: Physics Recovery & Held-Out Coverage

- **Scenarios Evaluated:** 7
- **Interval Coverage Rate:** **100.0%** (Target threshold: ≥ 80.0%)
- **Mean Speed Estimation Bias:** `-0.5678 km/h`
- **Mean Absolute Speed Error:** `0.8912 km/h`
- **Max Absolute Speed Error:** `3.7112 km/h`
- **Mean Track Fit RMSE:** `0.0709 m`
- **Refusal on Missing Calibration:** `PASS (Strict Abstention)`

### Scenario Detail Matrix

| Scenario | Description | Truth (km/h) | Est (km/h) | 90% Interval (km/h) | Error | Inside Interval? | Fit RMSE (m) | Status |
|---|---|---|---|---|---|---|---|---|
| `constant_slow` | Low-speed steady motion (20 km/h) under sub-pixel sensor noise | 20.0 | 19.93 | [12.58, 27.27] | 0.075 km/h | ✅ Yes | 0.0192 | ✅ PASS |
| `constant_fast` | Highway-speed steady motion (80 km/h) with 1px sensor jitter | 80.0 | 80.17 | [68.70, 91.64] | 0.167 km/h | ✅ Yes | 0.0510 | ✅ PASS |
| `moderate_braking` | Urban braking from 50 km/h at 4.0 m/s2 with 5% sporadic frame drops | 50.0 | 49.98 | [40.47, 59.49] | 0.021 km/h | ✅ Yes | 0.0397 | ✅ PASS |
| `hard_braking` | Emergency stop from 60 km/h at 8.0 m/s2 under 1.5px noise and 10% drop | 60.0 | 56.29 | [39.48, 73.10] | 3.711 km/h | ✅ Yes | 0.0784 | ✅ PASS |
| `noisy_sparse` | Low speed (35 km/h) with severe noise (3px) and 25% dropped frames | 35.0 | 35.80 | [5.57, 66.04] | 0.803 km/h | ✅ Yes | 0.1430 | ✅ PASS |
| `severe_decel_high_speed` | High speed (90 km/h) with sharp deceleration (9.0 m/s2) and 15% drop | 90.0 | 89.43 | [68.25, 110.61] | 0.570 km/h | ✅ Yes | 0.0942 | ✅ PASS |
| `uncalibrated_refusal` | Uncalibrated footage; system must explicitly abstain from metric speeds | *None* | *Refused* | *N/A* | *N/A* | *Refused* | *N/A* | ✅ PASS |

---

## Gate G6: Cross-Process Reproducibility & Assumption Sensitivity

Evaluates whether numerical optimization and rival searches produce identical outputs across distinct OS process instances, and verifies responsiveness to underlying priors.

| Check | Status | Evidence |
|---|---|---|
| `cross_process_dynamics_determinism` | ✅ PASS | Process A SHA: `7364dcaa4deda50a...`, Process B SHA: `7364dcaa4deda50a...` (Exact Match: True) |
| `cross_process_rival_search_determinism` | ✅ PASS | Search ID: `829360bd585c0ba2a1936df4314fe54466d1`, Candidates: 1321, Rivals: 10 (Exact Match: True) |
| `assumption_sensitivity_responsiveness` | ✅ PASS | Speed Δ (6.1885m vs 2.4169m), Decel Δ (41.8933m vs 8.2616m) |

---

## Gate G8: Rival Hypothesis Search & Edge Cases

Evaluates rival search behaviors across multi-camera and single-camera edge cases:

| Scenario | Description | Status | Evidence / Disclosed Behavior |
|---|---|---|---|
| `planted_disambiguation` | Planted Disambiguation | ✅ PASS | Single-view ambiguous (10 rivals found); 2nd view disambiguated (10 rejected by evidence: `Second-view residual for rival is 2.447 m (> 1.500 m); primary is 0.000 m (≤ threshold).`) |
| `no_rival_found` | No Rival Found | ✅ PASS | Rivals count = 0; clean refusal message generated: `No acceptable materially different rival found in searched bounds; speed=(4...` (1301 evaluated) |
| `inadequate_second_view` | Inadequate Second View | ✅ PASS | All rivals marked 'unresolved' when 2nd view lacks shared frame, calibration, or points. Notes: `Second view is inadequate; it was not used to reject rivals.` |

---

## Forensic Disclosures & Limitations

- **Synthetic Data Benchmark:** All scenarios were evaluated using mathematically generated kinematic trajectories with simulated sensor noise and frame dropouts. No real crash video was processed.
- **Empirical Coverage Validation:** The 100% empirical interval coverage on this held-out suite confirms that the Monte Carlo error propagation model accounts for frame dropouts, sensor jitter, and homography uncertainty.
- **Explicit Disambiguation Prerequisite:** Second-view rejection strictly requires verified synchronization, calibration, and shared coordinate frames; absent those preconditions, alternatives remain honestly categorized as 'unresolved'.

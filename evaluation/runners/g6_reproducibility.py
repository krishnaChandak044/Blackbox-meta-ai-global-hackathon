"""G6 Reproducibility and Assumption Sensitivity Test Runner.

Verifies:
1. Cross-process bit-level determinism for dynamics inference.
2. Cross-process bit-level determinism for rival hypothesis search.
3. Assumption sensitivity responsiveness: verifying that changes to underlying
   parameters/priors produce responsive sensitivity records rather than static stubs.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.counterfactual.simulator import compute_sensitivity
from engine.dynamics.inference import run_inference
from engine.dynamics.models import DynamicsResult
from engine.rival.hypothesis_search import search_rivals
from services.api.db.revision import canonical_json


# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------

def _make_benchmark_track(seed: int = 42) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    rng = np.random.default_rng(seed)
    times = np.linspace(0.0, 2.5, 63)
    v0 = 50.0 / 3.6  # 50 km/h
    decel = 4.0
    onset = 1.0
    obs: list[dict[str, Any]] = []
    for i, ts in enumerate(times):
        if ts <= onset:
            dist = v0 * ts
        else:
            dt = ts - onset
            dt_stop = v0 / decel
            bdt = min(dt, dt_stop)
            dist = v0 * onset + v0 * bdt - 0.5 * decel * bdt**2
        obs.append({
            "frame_index": i,
            "presentation_ts_s": float(ts),
            "world_x_m": float(dist + rng.normal(0, 0.02)),
            "world_y_m": float(rng.normal(0, 0.02)),
            "localisation_sigma_m": 0.02,
        })
    calibration = {
        "metres_per_pixel": 0.05,
        "homography_rmse_px": 0.5,
        "scale_relative_error": 0.002,
        "homography_fit_id": "g6-synth-cal",
    }
    vfr = {
        "has_vfr": False,
        "pts_available": True,
        "mean_frame_duration_s": 0.04,
        "frame_duration_sigma_s": 0.000001,
        "model_speed_bound_ms": 0.05,
        "timestamp_metadata": "g6-synth",
    }
    params = {
        "bounds": {"max_speed_ms": 50.0, "max_accel_ms2": 15.0},
        "try_two_segment": True,
    }
    return obs, calibration, vfr, params


# ---------------------------------------------------------------------------
# Cross-Process Subprocess Helpers
# ---------------------------------------------------------------------------

_SUBPROCESS_INFERENCE_CODE = """
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from engine.dynamics.inference import run_inference
from services.api.db.revision import canonical_json
from dataclasses import asdict

with open(sys.argv[2], 'r', encoding='utf-8') as f:
    payload = json.load(f)

res = run_inference(
    observations=payload['observations'],
    calibration=payload['calibration'],
    vfr_meta=payload['vfr'],
    params=payload['params'],
    track_id='g6-track',
    track_version_hash='hash-1',
    media_sha256='media-1',
    software_revision='rev-1',
    seed=payload['seed'],
)

# Convert dataclass to dict and canonical JSON hash
data = asdict(res)
raw_json = canonical_json(data)
sha = hashlib.sha256(raw_json).hexdigest()

out = {
    'run_id': res.run_id,
    'entry_speed_kmh': res.entry_speed_kmh,
    'entry_speed_lo_kmh': res.entry_speed_lo_kmh,
    'entry_speed_hi_kmh': res.entry_speed_hi_kmh,
    'mean_decel_ms2': res.mean_decel_ms2,
    'sha256': sha,
    'canonical_json': raw_json.decode('utf-8'),
}
print(json.dumps(out))
"""

_SUBPROCESS_RIVAL_CODE = """
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from engine.rival.hypothesis_search import search_rivals
from services.api.db.revision import canonical_json
from dataclasses import asdict

with open(sys.argv[2], 'r', encoding='utf-8') as f:
    payload = json.load(f)

res = search_rivals(
    primary_run=payload['primary'],
    observations=payload['observations'],
    calibration=payload['calibration'],
    params=payload['params'],
    seed=payload['seed'],
)

data = asdict(res)
raw_json = canonical_json(data)
sha = hashlib.sha256(raw_json).hexdigest()

out = {
    'search_id': res.manifest.search_id,
    'n_evaluated': res.manifest.n_candidates_evaluated,
    'rival_count': len(res.rivals),
    'sha256': sha,
    'canonical_json': raw_json.decode('utf-8'),
}
print(json.dumps(out))
"""


def _run_subprocess_task(code: str, payload: dict[str, Any], temp_dir: Path, tag: str) -> dict[str, Any]:
    input_file = temp_dir / f"payload_{tag}.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", code, str(_ROOT), str(input_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Gate 6 Verification Functions
# ---------------------------------------------------------------------------

def verify_cross_process_inference(temp_dir: Path) -> dict[str, Any]:
    """Runs inference in two independent Python processes; tests bitwise equality."""
    obs, cal, vfr, params = _make_benchmark_track(seed=42)
    payload = {
        "observations": obs,
        "calibration": cal,
        "vfr": vfr,
        "params": params,
        "seed": 98765,
    }

    sub_a = _run_subprocess_task(_SUBPROCESS_INFERENCE_CODE, payload, temp_dir, "inf_a")
    sub_b = _run_subprocess_task(_SUBPROCESS_INFERENCE_CODE, payload, temp_dir, "inf_b")

    hash_match = (sub_a["sha256"] == sub_b["sha256"])
    id_match = (sub_a["run_id"] == sub_b["run_id"])
    speed_match = (sub_a["entry_speed_kmh"] == sub_b["entry_speed_kmh"])
    decel_match = (sub_a["mean_decel_ms2"] == sub_b["mean_decel_ms2"])
    json_match = (sub_a["canonical_json"] == sub_b["canonical_json"])

    passed = hash_match and id_match and speed_match and decel_match and json_match
    return {
        "check": "cross_process_dynamics_determinism",
        "passed": passed,
        "process_a_sha256": sub_a["sha256"],
        "process_b_sha256": sub_b["sha256"],
        "run_id": sub_a["run_id"],
        "entry_speed_kmh": sub_a["entry_speed_kmh"],
        "mean_decel_ms2": sub_a["mean_decel_ms2"],
        "exact_canonical_match": json_match,
    }


def verify_cross_process_rival_search(temp_dir: Path) -> dict[str, Any]:
    """Runs rival search in two independent Python processes; tests bitwise equality."""
    obs, cal, _, _ = _make_benchmark_track(seed=42)
    primary = {
        "run_id": "primary-test-run",
        "entry_speed_kmh": 50.0,
        "mean_decel_ms2": 4.0,
        "braking_onset_s": 1.0,
    }
    options = {
        "n_grid": 11,
        "acceptance_threshold_m": 1.0,
        "speed_lo_kmh": 40.0,
        "speed_hi_kmh": 60.0,
    }
    payload = {
        "primary": primary,
        "observations": obs,
        "calibration": cal,
        "params": options,
        "seed": 54321,
    }

    sub_a = _run_subprocess_task(_SUBPROCESS_RIVAL_CODE, payload, temp_dir, "riv_a")
    sub_b = _run_subprocess_task(_SUBPROCESS_RIVAL_CODE, payload, temp_dir, "riv_b")

    hash_match = (sub_a["sha256"] == sub_b["sha256"])
    search_id_match = (sub_a["search_id"] == sub_b["search_id"])
    eval_count_match = (sub_a["n_evaluated"] == sub_b["n_evaluated"])
    rival_count_match = (sub_a["rival_count"] == sub_b["rival_count"])

    passed = hash_match and search_id_match and eval_count_match and rival_count_match
    return {
        "check": "cross_process_rival_search_determinism",
        "passed": passed,
        "process_a_sha256": sub_a["sha256"],
        "process_b_sha256": sub_b["sha256"],
        "search_id": sub_a["search_id"],
        "candidates_evaluated": sub_a["n_evaluated"],
        "rival_count": sub_a["rival_count"],
        "exact_canonical_match": (sub_a["canonical_json"] == sub_b["canonical_json"]),
    }


def verify_assumption_sensitivity_responsiveness() -> dict[str, Any]:
    """Verifies that altering model priors changes the sensitivity record quantitatively."""
    obs, cal, vfr, params = _make_benchmark_track(seed=42)
    baseline = run_inference(obs, cal, vfr, params, "track_sens", "th", "mh", "rev", seed=42)

    # 1. Standard default perturbations
    sens_default = compute_sensitivity(baseline)

    # 2. Perturbation with tighter speed shift (±2 km/h instead of ±5 km/h)
    sens_narrow = compute_sensitivity(
        baseline,
        perturbations={
            "entry_speed_override_kmh": [
                baseline.entry_speed_kmh - 2.0,
                baseline.entry_speed_kmh + 2.0,
            ],
            "braking_onset_shift_s": [-0.5, 0.5],
            "decel_override_ms2": [
                baseline.mean_decel_ms2 - 1.0,
                baseline.mean_decel_ms2 + 1.0,
            ],
        },
    )

    # 3. Perturbation with severe deceleration perturbation
    sens_severe_decel = compute_sensitivity(
        baseline,
        perturbations={
            "entry_speed_override_kmh": [
                baseline.entry_speed_kmh - 5.0,
                baseline.entry_speed_kmh + 5.0,
            ],
            "braking_onset_shift_s": [-0.5, 0.5],
            "decel_override_ms2": [
                baseline.mean_decel_ms2 - 2.5,
                baseline.mean_decel_ms2 + 2.5,
            ],
        },
    )

    # Extract speed entry delta
    speed_default = next(s for s in sens_default if s.parameter == "entry_speed_override_kmh")
    speed_narrow = next(s for s in sens_narrow if s.parameter == "entry_speed_override_kmh")

    # Extract decel entry delta
    decel_default = next(s for s in sens_default if s.parameter == "decel_override_ms2")
    decel_severe = next(s for s in sens_severe_decel if s.parameter == "decel_override_ms2")

    speed_sens_responsive = abs(speed_default.stopping_distance_delta_m) > abs(speed_narrow.stopping_distance_delta_m)
    decel_sens_responsive = abs(decel_severe.stopping_distance_delta_m) > abs(decel_default.stopping_distance_delta_m)

    passed = speed_sens_responsive and decel_sens_responsive

    return {
        "check": "assumption_sensitivity_responsiveness",
        "passed": passed,
        "default_speed_delta_m": round(speed_default.stopping_distance_delta_m, 4),
        "narrow_speed_delta_m": round(speed_narrow.stopping_distance_delta_m, 4),
        "default_decel_delta_m": round(decel_default.stopping_distance_delta_m, 4),
        "severe_decel_delta_m": round(decel_severe.stopping_distance_delta_m, 4),
        "responsiveness_verified": passed,
    }


def run_g6_suite(temp_dir: Path | None = None) -> dict[str, Any]:
    """Runs complete G6 gate evaluation."""
    import tempfile
    td = temp_dir or Path(tempfile.mkdtemp(prefix="g6_eval_"))

    checks = [
        verify_cross_process_inference(td),
        verify_cross_process_rival_search(td),
        verify_assumption_sensitivity_responsiveness(),
    ]

    all_passed = all(c["passed"] for c in checks)
    return {
        "gate": "G6-reproducibility-and-sensitivity",
        "status": "PASS" if all_passed else "FAIL",
        "checks": checks,
    }


if __name__ == "__main__":
    result = run_g6_suite()
    print(f"G6 Suite Status: {result['status']}")
    for c in result["checks"]:
        status_icon = "✅" if c["passed"] else "❌"
        print(f"  {status_icon} {c['check']}")

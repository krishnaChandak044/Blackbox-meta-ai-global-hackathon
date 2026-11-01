"""Deterministic backend G7 scene contract acceptance runner."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.scene3d import build_scene_payload


def run_g7_backend(samples_per_track: int = 50) -> dict[str, Any]:
    if samples_per_track < 50:
        raise ValueError("G7 backend scorecard requires at least 100 observed samples")
    tracks = []
    fitted = []
    counterfactual = []
    for track_index, category in enumerate(("vehicle", "pedestrian")):
        observed, fitted_points, scenario_points = [], [], []
        for frame in range(samples_per_track):
            timestamp = frame / 25.0
            x = -12.0 + frame * 0.14 + track_index * 1.75
            y = 4.0 + math.sin(frame / 12.0) * 0.35 - track_index * 1.2
            point = {"frame_index": frame, "presentation_ts_s": timestamp,
                     "world_x_m": x, "world_y_m": y, "sigma_m": 0.08,
                     "is_interpolated": frame % 11 == 0}
            observed.append(point)
            fitted_points.append({**point, "pos_sigma_x_m": 0.05, "pos_sigma_y_m": 0.06})
            scenario_points.append({**point, "world_x_m": x + 0.3, "world_y_m": y - 0.1})
        track_id = f"fixture-{category}"
        tracks.append({"track_id": track_id, "category": category,
                       "is_human_confirmed": track_index == 0, "points": observed})
        fitted.append({"id": f"fit-{track_id}", "interval_type": "illustrative_range",
                       "fitted_points_json": json.dumps(fitted_points)})
        if track_index == 0:
            counterfactual.append({"id": "cf-fixture", "baseline_run_id": "fit-fixture-vehicle",
                "illustrative_label": "ILLUSTRATIVE — preregistered G7 fixture",
                "simulated_points_json": json.dumps(scenario_points)})

    vehicle_observations = tracks[0]["points"]
    rival = {"id": "rival-fixture", "manifest_json": "{}", "track_observations": vehicle_observations,
             "rivals_json": json.dumps([{"rank": 1, "residual": 0.4,
                 "disambiguation_status": "unresolved",
                 "params": {"entry_speed_kmh": 24.0, "deceleration_ms2": 4.0,
                            "braking_onset_s": 0.0}}])}
    scene = build_scene_payload(case_id="g7-case", media_id="g7-media", media_sha256="a" * 64,
        calibration={"id": "g7-calibration"}, tracks=tracks, dynamics_runs=fitted,
        counterfactuals=counterfactual, rivals=[rival])

    errors = []
    frame_links_valid = True
    for source in tracks:
        mapped = next(item for item in scene["objects"] if item["track_id"] == source["track_id"])
        source_map = {point["frame_index"]: point for point in source["points"]}
        for point in mapped["samples"]:
            expected = source_map[point["frame_index"]]
            errors.extend((abs(point["position_2d_m"]["x"] - expected["world_x_m"]),
                           abs(point["position_2d_m"]["y"] - expected["world_y_m"]),
                           abs(point["position_m"]["z"])))
            frame_links_valid &= point["source"] == {"media_id": "g7-media", "frame_index": point["frame_index"]}
            frame_links_valid &= point["provenance"] == ("interpolated_observation" if expected["is_interpolated"] else "observed_track")

    fitted_count = sum(len(path["samples"]) for path in scene["fitted_paths"])
    cf_count = sum(len(path["samples"]) for path in scene["counterfactual_paths"])
    rival_hypotheses = [hypothesis for group in scene["rival_paths"] for hypothesis in group["hypotheses"]]
    max_error = max(errors, default=math.inf)
    rms_error = math.sqrt(sum(error * error for error in errors) / len(errors)) if errors else math.inf
    assert len(errors) == samples_per_track * 2 * 3
    assert max_error <= 1e-6 and rms_error <= 1e-6
    assert fitted_count == samples_per_track * 2
    assert cf_count == samples_per_track
    assert rival_hypotheses and len(rival_hypotheses[0]["samples"]) == samples_per_track
    assert frame_links_valid
    assert scene["camera_pose"]["status"] == "unknown"
    assert "ILLUSTRATIVE" in scene["synthetic_view_label"]
    assert "ILLUSTRATIVE" in scene["counterfactual_paths"][0]["illustrative_label"]
    assert "ILLUSTRATIVE" in scene["rival_paths"][0]["illustrative_label"]

    return {"gate": "G7-backend-scene-contract", "status": "PASS",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_count": 1, "track_types": ["vehicle", "pedestrian"],
        "observed_samples": samples_per_track * 2, "coordinate_components_compared": len(errors),
        "fitted_samples": fitted_count, "counterfactual_samples": cf_count,
        "rival_hypotheses_with_paths": len(rival_hypotheses),
        "units": "metres", "tolerance_m": 1e-6, "max_error_m": max_error,
        "rms_error_m": rms_error, "frame_links_and_provenance_valid": frame_links_valid,
        "unknown_camera_pose_preserved": True, "simulated_layers_labelled_illustrative": True,
        "limitations": ["Backend adapter only; browser pixels and interactive controls were not measured.",
            "Ground-plane coordinates are exact pass-through values; z is fixed to zero.",
            "Rival path samples are bounded model projections, not observations or confidence intervals."]}


def main() -> None:
    result = run_g7_backend()
    output_path = Path("evaluation/scorecards/phase5_g7_backend_2026-11-01.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"- **{key.replace('_', ' ')}:** {value}" for key, value in result.items())
    output_path.write_text(f"# Phase 5 G7 backend scene scorecard\n\n{rows}\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"scorecard: {output_path}")


if __name__ == "__main__":
    main()

"""Renderer-neutral, provenance-preserving scene payload builder.

This module maps supplied engine values to a scene contract. It does not infer
motion, camera poses, dimensions, or missing observations.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

SCENE_SCHEMA_VERSION = "1.0.0"


def build_scene_payload(*, case_id: str, media_id: str, media_sha256: str,
                        calibration: dict[str, Any] | None,
                        tracks: list[dict[str, Any]], dynamics_runs: list[dict[str, Any]],
                        counterfactuals: list[dict[str, Any]] | None = None,
                        rivals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a deterministic 3D scene from exact 2D engine samples."""
    objects = []
    for track in sorted(tracks, key=lambda row: row["track_id"]):
        points = sorted(track.get("points", []), key=lambda row: (row["presentation_ts_s"], row["frame_index"]))
        samples = []
        for point in points:
            x, y = point.get("world_x_m"), point.get("world_y_m")
            if x is None or y is None:
                continue
            samples.append({
                "frame_index": int(point["frame_index"]),
                "presentation_ts_s": float(point["presentation_ts_s"]),
                "position_m": {"x": float(x), "y": float(y), "z": 0.0},
                "position_2d_m": {"x": float(x), "y": float(y)},
                "uncertainty_sigma_m": point.get("sigma_m"),
                "provenance": "observed_track" if not point.get("is_interpolated", False) else "interpolated_observation",
                "source": {"media_id": media_id, "frame_index": int(point["frame_index"])},
            })
        objects.append({
            "track_id": track["track_id"],
            "class": track.get("category", "unknown"),
            "review_status": "reviewer_confirmed" if track.get("is_human_confirmed") else "unconfirmed",
            "geometry": {"source": "generic_proxy", "label": "ILLUSTRATIVE geometry; no dimensions inferred"},
            "samples": samples,
        })

    fitted = []
    for run in sorted(dynamics_runs, key=lambda row: row["id"]):
        fitted.append({"run_id": run["id"], "path_type": "fitted", "provenance": "measured_model_output",
                       "interval_type": run.get("interval_type"),
                       "samples": _path_samples(run.get("fitted_points_json"), media_id, simulated=False)})
    counterfactual_paths = []
    for row in sorted(counterfactuals or [], key=lambda item: item["id"]):
        counterfactual_paths.append({"run_id": row["id"], "baseline_run_id": row["baseline_run_id"],
                                     "path_type": "counterfactual", "provenance": "SIMULATED",
                                     "illustrative_label": row.get("illustrative_label") or "ILLUSTRATIVE — model scenario, not observed fact",
                                     "samples": _path_samples(row.get("simulated_points_json"), media_id, simulated=True)})
    rival_paths = []
    for row in sorted(rivals or [], key=lambda item: item["id"]):
        hypotheses = json.loads(row.get("rivals_json") or "[]")
        observations = row.get("track_observations") or []
        rival_paths.append({"search_id": row["id"], "path_type": "rival_hypotheses", "provenance": "SIMULATED",
                            "illustrative_label": "ILLUSTRATIVE — bounded rival model",
                            "manifest_json": row.get("manifest_json"),
                            "hypotheses": [{"rank": hypothesis.get("rank"),
                                "params": hypothesis.get("params"),
                                "residual_m": hypothesis.get("residual"),
                                "disambiguation_status": hypothesis.get("disambiguation_status"),
                                "samples": _rival_samples(hypothesis, observations)}
                                for hypothesis in hypotheses]})
    return {
        "scene_id": f"{case_id}:{media_id}", "schema_version": SCENE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case_id, "media_id": media_id, "media_sha256": media_sha256,
        "coordinate_system": {"handedness": "right", "units": "metres", "ground_plane": "z=0",
                               "origin": "calibration-defined", "calibration_fit_id": (calibration or {}).get("id"),
                               "transform_source": "stored engine world coordinates; no browser recalibration"},
        "camera_pose": {"status": "unknown", "reason": "camera extrinsics are not currently stored"},
        "objects": objects, "fitted_paths": fitted,
        "counterfactual_paths": counterfactual_paths, "rival_paths": rival_paths,
        "synthetic_view_label": "ILLUSTRATIVE — NOT SOURCE FOOTAGE",
        "limitations": ["z positions, dimensions, camera pose, and unseen surfaces are not inferred.",
                        "Scene samples preserve source engine coordinates; display interpolation is not included."],
    }


def _path_samples(raw: str | None, media_id: str, *, simulated: bool) -> list[dict[str, Any]]:
    if not raw:
        return []
    values = json.loads(raw)
    result = []
    for point in values:
        sample = {"frame_index": int(point["frame_index"]),
                  "presentation_ts_s": float(point["presentation_ts_s"]),
                  "position_m": {"x": float(point["world_x_m"]), "y": float(point["world_y_m"]), "z": 0.0},
                  "position_2d_m": {"x": float(point["world_x_m"]), "y": float(point["world_y_m"])},
                  "provenance": "SIMULATED" if simulated else "fitted_model_output"}
        if not simulated:
            sample["source"] = {"media_id": media_id, "frame_index": int(point["frame_index"])}
            if "pos_sigma_x_m" in point and "pos_sigma_y_m" in point:
                sample["uncertainty_sigma_xy_m"] = {"x": float(point["pos_sigma_x_m"]),
                                                    "y": float(point["pos_sigma_y_m"]),
                                                    "coverage": "illustrative; not empirically validated"}
        result.append(sample)
    return result


def _rival_samples(hypothesis: dict[str, Any], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project a bounded rival parameter set over the observed time samples."""
    params = hypothesis.get("params") or {}
    if len(observations) < 2 or any(
        params.get(key) is None for key in ("entry_speed_kmh", "deceleration_ms2", "braking_onset_s")
    ):
        return []
    points = sorted(observations, key=lambda point: point["presentation_ts_s"])
    first, last = points[0], points[-1]
    dx = float(last["world_x_m"]) - float(first["world_x_m"])
    dy = float(last["world_y_m"]) - float(first["world_y_m"])
    norm = math.hypot(dx, dy)
    speed = float(params["entry_speed_kmh"]) / 3.6
    deceleration = float(params["deceleration_ms2"])
    if norm <= 1e-9 or speed < 0 or deceleration <= 0:
        return []
    direction_x, direction_y = dx / norm, dy / norm
    start = float(first["presentation_ts_s"])
    onset_delay = max(0.0, float(params["braking_onset_s"]) - start)
    stop_duration = speed / deceleration
    output = []
    for point in points:
        elapsed = max(0.0, float(point["presentation_ts_s"]) - start)
        pre_brake = min(elapsed, onset_delay)
        brake_elapsed = min(max(0.0, elapsed - onset_delay), stop_duration)
        distance = speed * pre_brake + speed * brake_elapsed - 0.5 * deceleration * brake_elapsed**2
        x = float(first["world_x_m"]) + direction_x * distance
        y = float(first["world_y_m"]) + direction_y * distance
        output.append({"frame_index": int(point["frame_index"]),
                       "presentation_ts_s": float(point["presentation_ts_s"]),
                       "position_m": {"x": x, "y": y, "z": 0.0},
                       "position_2d_m": {"x": x, "y": y},
                       "provenance": "SIMULATED",
                       "uncertainty": "not provided by bounded rival search"})
    return output

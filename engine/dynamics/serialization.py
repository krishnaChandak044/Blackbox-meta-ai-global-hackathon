"""Rebuild immutable engine dataclasses from persisted JSON payloads."""

from __future__ import annotations

import json
from typing import Any

from engine.dynamics.models import (
    BrakingOnset,
    DynamicsResult,
    FitQuality,
    FittedPoint,
    IdentifiabilityCertificate,
    UncertaintyBundle,
    UncertaintyContribution,
)


def dynamics_result_from_storage(row: Any) -> DynamicsResult:
    points = [FittedPoint(**item) for item in (json.loads(row.fitted_points_json) if row.fitted_points_json else [])]
    uncertainty_data = json.loads(row.uncertainty_json or "{}")
    for name in ("pixel_localisation", "homography_reprojection", "scale_calibration", "frame_timestamp", "model_assumption"):
        uncertainty_data[name] = UncertaintyContribution(**uncertainty_data[name])
    uncertainty = UncertaintyBundle(**uncertainty_data)
    cert_data = json.loads(row.certificates_json or "{}")
    certificates = {name: IdentifiabilityCertificate(**value) for name, value in cert_data.items()}
    fit_quality = FitQuality(**json.loads(row.fit_quality_json or "{}"))
    onset_data = json.loads(row.braking_onset_json) if row.braking_onset_json else None
    if onset_data:
        onset_data["certificate"] = IdentifiabilityCertificate(**onset_data["certificate"])
        onset = BrakingOnset(**onset_data)
    else:
        onset = None
    return DynamicsResult(
        run_id=row.id,
        track_id=row.track_id,
        track_version_hash=row.track_version_hash,
        calibration_fit_id=row.calibration_fit_id,
        media_sha256=row.media_sha256,
        model_name=row.model_name,
        model_version=row.model_version,
        software_revision=row.software_revision,
        seed=row.seed,
        params_json=row.params_json,
        fitted_points=points,
        entry_speed_kmh=row.entry_speed_kmh,
        entry_speed_lo_kmh=row.entry_speed_lo_kmh,
        entry_speed_hi_kmh=row.entry_speed_hi_kmh,
        mean_decel_ms2=row.mean_decel_ms2,
        mean_decel_lo_ms2=row.mean_decel_lo_ms2,
        mean_decel_hi_ms2=row.mean_decel_hi_ms2,
        braking_onset=onset,
        uncertainty=uncertainty,
        certificates=certificates,
        fit_quality=fit_quality,
        interval_type=row.interval_type,
    )

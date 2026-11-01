"""Focused Phase 5 backend contract tests; no live services or external models."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from engine.rescue.missing_evidence import rank_evidence_needs
from engine.scene3d import build_scene_payload
from services.api.db.models import (
    Base,
    Case,
    CaseStatus,
    ExportRecord,
    MediaStatus,
    ReviewerAction,
    SourceMedia,
)
from services.api.routes.atlas import SCOPE_VERSION, ConsentInput, ContributionInput
from services.api.routes.exports import _revision_hash
from services.worker.jobs.export import _build


def test_scene_contract_preserves_2d_coordinates_and_labels_generated_paths():
    payload = build_scene_payload(
        case_id="case-1", media_id="media-1", media_sha256="abc",
        calibration={"id": "fit-1"},
        tracks=[{"track_id": "track-1", "category": "vehicle", "is_human_confirmed": True,
                 "points": [{"frame_index": 7, "presentation_ts_s": 0.7,
                             "world_x_m": 12.5, "world_y_m": -2.0, "sigma_m": 0.3}]}],
        dynamics_runs=[{"id": "run-1", "interval_type": "illustrative_range",
                        "fitted_points_json": json.dumps([{"frame_index": 7, "presentation_ts_s": 0.7,
                            "world_x_m": 12.5, "world_y_m": -2.0, "pos_sigma_x_m": 0.4, "pos_sigma_y_m": 0.5}])}],
        counterfactuals=[{"id": "cf-1", "baseline_run_id": "run-1",
            "simulated_points_json": json.dumps([{"frame_index": 7, "presentation_ts_s": 0.7,
                "world_x_m": 13.0, "world_y_m": -2.0}])}],
        rivals=[{"id": "rival-1", "manifest_json": "{}", "rivals_json": json.dumps([
            {"rank": 1, "params": {"entry_speed_kmh": 20.0, "deceleration_ms2": 4.0,
                                     "braking_onset_s": 0.0}, "residual": 0.2,
             "disambiguation_status": "unresolved"}]), "track_observations": [
                 {"frame_index": 7, "presentation_ts_s": 0.7, "world_x_m": 12.5, "world_y_m": -2.0},
                 {"frame_index": 9, "presentation_ts_s": 1.0, "world_x_m": 13.0, "world_y_m": -2.0}]}],
    )
    observed = payload["objects"][0]["samples"][0]
    fitted = payload["fitted_paths"][0]["samples"][0]
    simulated = payload["counterfactual_paths"][0]
    assert observed["position_2d_m"] == {"x": 12.5, "y": -2.0}
    assert fitted["position_2d_m"] == observed["position_2d_m"]
    assert simulated["provenance"] == "SIMULATED"
    assert "ILLUSTRATIVE" in simulated["illustrative_label"]
    assert len(payload["rival_paths"][0]["hypotheses"][0]["samples"]) == 2
    assert payload["rival_paths"][0]["hypotheses"][0]["samples"][0]["position_2d_m"] == {"x": 12.5, "y": -2.0}
    assert payload["camera_pose"]["status"] == "unknown"


def test_radar_never_invents_sources_and_uses_only_verified_deadline_for_urgency():
    certificates = {
        "entry_speed": {"status": "not_identifiable", "limiting_source": "scale_calibration"},
        "braking_onset": {"status": "conditional", "limiting_source": "frame_timestamp"},
    }
    rows = rank_evidence_needs(certificates)
    assert all(row["availability"] == "unknown" for row in rows)
    assert all(row["retention_deadline"] is None for row in rows)
    urgent = rank_evidence_needs(certificates,
        known_sources=[{"need_key": "measure_scene_distance", "verified": True}],
        verified_deadlines={"measure_scene_distance": 2.0})
    scale = next(row for row in urgent if row["need_key"] == "measure_scene_distance")
    assert scale["availability"] == "human_verified_source"
    assert scale["retention_deadline"]["basis"] == "user_verified"
    assert "not a probability" in scale["reduction_metric"]


def test_atlas_contract_requires_scoped_consent_and_rejects_unbounded_or_pii_fields():
    assert ConsentInput(opted_in=True).scope_version == SCOPE_VERSION
    with pytest.raises(ValidationError):
        ConsentInput(opted_in=True, scope_version="all-case-data")
    base = {"source_run_id": "run-1", "coarse_cell": "u4pr", "time_bucket": "2026-Q4",
            "conflict_type": "crossing", "road_user_mix": {"pedestrian": 2},
            "metrics": {"near_miss_count": 1}, "reviewer_confirmed": True}
    assert ContributionInput(**base).coarse_cell == "u4pr"
    with pytest.raises(ValidationError):
        ContributionInput(**{**base, "metrics": {"person_name": 1}})
    with pytest.raises(ValidationError):
        ContributionInput(**{**base, "metrics": {"minimum_ttc_s": -0.5}})


@pytest.mark.asyncio
async def test_export_worker_rechecks_full_case_revision_and_writes_hashed_artifacts(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "phase5.sqlite"
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    media_file = tmp_path / "original.mp4"
    media_file.write_bytes(b"synthetic but byte-preserved fixture")
    media_hash = hashlib.sha256(media_file.read_bytes()).hexdigest()
    async with async_factory() as db:
        case = Case(id="case-export", title="Staged export", owner_id="tester", status=CaseStatus.DRAFT,
                    consent_given=False)
        db.add(case)
        await db.flush()
        db.add(SourceMedia(id="media-export", case_id=case.id, original_filename="staged.mp4",
            mime_type="video/mp4", byte_length=media_file.stat().st_size, sha256=media_hash,
            storage_path=str(media_file), status=MediaStatus.STORED))
        db.add(ReviewerAction(id="action-export", case_id=case.id, target_type="case",
            target_id=case.id, action="reviewed", after_json="{}", actor="tester"))
        await db.commit()
        revision = await _revision_hash(case.id, db)
        record = ExportRecord(id="export-1", case_id=case.id, case_revision_hash=revision,
                              status="running", created_by="tester")
        db.add(record)
        await db.commit()

    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    sync_engine = create_engine(f"sqlite:///{db_file}")
    with Session(sync_engine) as session:
        record = session.get(ExportRecord, "export-1")
        result = _build(session, record)
        session.commit()
        assert result["export_id"] == record.id
        assert Path(record.json_path).is_file()
        assert Path(record.pdf_path).is_file()
        assert Path(record.pdf_path).read_bytes().startswith(b"%PDF-1.4")
        manifest_bytes = Path(record.json_path).read_bytes()
        manifest = json.loads(manifest_bytes)
        assert manifest["manifest_sha256"] == record.manifest_sha256
        assert manifest["media"][0]["verified_sha256"] == media_hash
        assert manifest["media"][0]["integrity"] == "verified_at_export"
        assert hashlib.sha256(manifest_bytes).hexdigest() == record.json_sha256
        assert hashlib.sha256(Path(record.pdf_path).read_bytes()).hexdigest() == record.pdf_sha256
    sync_engine.dispose()
    await async_engine.dispose()

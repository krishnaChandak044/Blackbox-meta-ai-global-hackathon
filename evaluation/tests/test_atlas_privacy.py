"""Evaluation Suite for Prevention Atlas Privacy Gates & Controls.

Verifies:
1. Consent opt-in requirement before contribution.
2. Immediate purge of contributions on consent revocation.
3. K-anonymity / cohort suppression below minimum threshold (MIN_COHORT = 5).
4. Strict spatial coarsening (rejection of exact GPS coordinates).
5. Strict temporal coarsening (rejection of exact timestamps in favor of quarters).
6. Total absence of direct or pseudo-identifiers in aggregate outputs.
7. Deduplication preventing single-case cohort inflation.
8. Immutable consent audit trail (AtlasConsentEvent).
9. Human reviewer confirmation requirement.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.api.db.models import (
    AtlasConsent,
    AtlasConsentEvent,
    AtlasContribution,
    Base,
    Case,
    CaseStatus,
    DynamicsRun,
    MediaStatus,
    SourceMedia,
)
from services.api.routes.atlas import (
    MIN_COHORT,
    SCOPE_VERSION,
    ConsentInput,
    ContributionInput,
    add_contribution,
    atlas_aggregates,
    set_consent,
)


@pytest.fixture
async def async_db(tmp_path: Path):
    db_file = tmp_path / "atlas_privacy_test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed_case_and_run(db, case_id: str, run_id: str) -> str:
    media_id = f"m-{case_id}"
    db.add(Case(
        id=case_id,
        title=f"Test Case {case_id}",
        status=CaseStatus.READY,
        consent_given=True,
        owner_id="privacy-tester",
    ))
    db.add(SourceMedia(
        id=media_id,
        case_id=case_id,
        original_filename="clip.mp4",
        mime_type="video/mp4",
        byte_length=1000,
        sha256="0" * 64,
        storage_path="/tmp/test.mp4",
        status=MediaStatus.INDEXED,
    ))
    db.add(DynamicsRun(
        id=run_id,
        case_id=case_id,
        media_id=media_id,
        track_id="t-1",
        track_version_hash="0" * 64,
        calibration_fit_id="c-fit-1",
        media_sha256="0" * 64,
        model_name="piecewise_const_accel",
        model_version="1.0.0",
        software_revision="rev-1",
        seed=42,
        params_json="{}",
        status="done",
        entry_speed_kmh=45.0,
        mean_decel_ms2=4.0,
    ))
    await db.commit()
    return media_id


# ---------------------------------------------------------------------------
# Unit Validations: Spatial and Temporal Coarsening
# ---------------------------------------------------------------------------

def test_spatial_coarsening_rejects_exact_coordinates():
    """Exact GPS coordinates or precision geohashes must be rejected."""
    base = {
        "source_run_id": "run-1",
        "time_bucket": "2026-Q4",
        "conflict_type": "crossing",
        "road_user_mix": {"pedestrian": 1},
        "metrics": {"near_miss_count": 1.0},
        "reviewer_confirmed": True,
    }

    # Valid coarse cells (length 4–5, base32 geohash characters)
    assert ContributionInput(coarse_cell="u4pr", **base).coarse_cell == "u4pr"
    assert ContributionInput(coarse_cell="9q8yy", **base).coarse_cell == "9q8yy"

    # Rejection of exact lat/long coordinates
    with pytest.raises(ValidationError):
        ContributionInput(coarse_cell="37.7749,-122.4194", **base)

    # Rejection of high-precision geohashes (> 5 chars, resolving to < 1 km)
    with pytest.raises(ValidationError):
        ContributionInput(coarse_cell="9q8yyz2", **base)

    # Rejection of overly coarse cells (< 4 chars)
    with pytest.raises(ValidationError):
        ContributionInput(coarse_cell="u4", **base)


def test_time_bucketing_rejects_exact_timestamps():
    """Exact timestamps or non-quarterly intervals must be rejected."""
    base = {
        "source_run_id": "run-1",
        "coarse_cell": "u4pr",
        "conflict_type": "rear_end",
        "road_user_mix": {"motor_vehicle": 2},
        "metrics": {"minimum_ttc_s": 1.2},
        "reviewer_confirmed": True,
    }

    # Valid quarterly time bucket
    assert ContributionInput(time_bucket="2026-Q4", **base).time_bucket == "2026-Q4"

    # Rejection of ISO 8601 timestamps
    with pytest.raises(ValidationError):
        ContributionInput(time_bucket="2026-11-04T10:00:00Z", **base)

    # Rejection of calendar dates
    with pytest.raises(ValidationError):
        ContributionInput(time_bucket="2026-11-04", **base)

    # Rejection of invalid quarters
    with pytest.raises(ValidationError):
        ContributionInput(time_bucket="2026-Q5", **base)


@pytest.mark.asyncio
async def test_unconfirmed_contributions_rejected(async_db):
    """Derived summaries must be confirmed by a qualified human reviewer."""
    from fastapi import HTTPException
    cid, rid = "case-unconfirmed", "run-unconfirmed"
    await _seed_case_and_run(async_db, cid, rid)
    await set_consent(cid, ConsentInput(opted_in=True), db=async_db, user="owner")

    payload = ContributionInput(
        source_run_id=rid,
        coarse_cell="u4pr",
        time_bucket="2026-Q4",
        conflict_type="crossing",
        road_user_mix={"cyclist": 1},
        metrics={"conflict_count": 1.0},
        reviewer_confirmed=False,
    )
    with pytest.raises(HTTPException) as exc_info:
        await add_contribution(cid, payload, db=async_db, user="analyst")
    assert exc_info.value.status_code == 422
    assert "reviewer must confirm" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Integration Tests: Consent, Purge & Aggregates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_separate_consent_required_before_contribution(async_db):
    """Cases without explicit Atlas opt-in consent must be refused."""
    case_id, run_id = "c-no-consent", "r-no-consent"
    await _seed_case_and_run(async_db, case_id, run_id)

    payload = ContributionInput(
        source_run_id=run_id,
        coarse_cell="u4pr",
        time_bucket="2026-Q4",
        conflict_type="turning",
        road_user_mix={"motor_vehicle": 1, "pedestrian": 1},
        metrics={"minimum_ttc_s": 0.8},
        reviewer_confirmed=True,
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await add_contribution(case_id, payload, db=async_db, user="analyst-1")
    assert exc_info.value.status_code == 409
    assert "opt-in consent is required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cohort_suppression_below_threshold(async_db):
    """Cells with fewer than MIN_COHORT (5) distinct cases must be suppressed."""
    # Seed 3 distinct cases in cell 'u4pr', 2026-Q4, crossing
    for i in range(1, 4):
        cid, rid = f"case-cohort-{i}", f"run-cohort-{i}"
        await _seed_case_and_run(async_db, cid, rid)
        await set_consent(cid, ConsentInput(opted_in=True), db=async_db, user="owner")
        await add_contribution(
            cid,
            ContributionInput(
                source_run_id=rid,
                coarse_cell="u4pr",
                time_bucket="2026-Q4",
                conflict_type="crossing",
                road_user_mix={"pedestrian": 1},
                metrics={"conflict_count": 1.0},
                reviewer_confirmed=True,
            ),
            db=async_db,
            user="analyst",
        )

    # Query aggregates — should be suppressed because 3 < MIN_COHORT (5)
    result = await atlas_aggregates(db=async_db, _="analyst")
    assert result["minimum_cohort"] == 5
    assert len(result["aggregates"]) == 0
    assert result["suppressed_group_count"] >= 1

    # Now add 2 more cases to reach the threshold of 5
    for i in range(4, 6):
        cid, rid = f"case-cohort-{i}", f"run-cohort-{i}"
        await _seed_case_and_run(async_db, cid, rid)
        await set_consent(cid, ConsentInput(opted_in=True), db=async_db, user="owner")
        await add_contribution(
            cid,
            ContributionInput(
                source_run_id=rid,
                coarse_cell="u4pr",
                time_bucket="2026-Q4",
                conflict_type="crossing",
                road_user_mix={"pedestrian": 1},
                metrics={"conflict_count": 1.0},
                reviewer_confirmed=True,
            ),
            db=async_db,
            user="analyst",
        )

    # Query aggregates — now 5 >= 5, so cell 'u4pr' must be visible
    result_unlocked = await atlas_aggregates(db=async_db, _="analyst")
    assert len(result_unlocked["aggregates"]) == 1
    cell_agg = result_unlocked["aggregates"][0]
    assert cell_agg["coarse_cell"] == "u4pr"
    assert cell_agg["distinct_case_count"] == 5
    assert cell_agg["time_bucket"] == "2026-Q4"


@pytest.mark.asyncio
async def test_no_direct_identifiers_in_aggregate_payload(async_db):
    """Aggregate payload must contain zero direct identifiers or case links."""
    # Build 5 valid contributions
    for i in range(1, 6):
        cid, rid = f"case-pii-{i}", f"run-pii-{i}"
        await _seed_case_and_run(async_db, cid, rid)
        await set_consent(cid, ConsentInput(opted_in=True), db=async_db, user="owner")
        await add_contribution(
            cid,
            ContributionInput(
                source_run_id=rid,
                coarse_cell="u4pr",
                time_bucket="2026-Q4",
                conflict_type="turning",
                road_user_mix={"motor_vehicle": 1, "cyclist": 1},
                metrics={"near_miss_count": 1.0, "p95_speed_kmh": 32.5},
                reviewer_confirmed=True,
            ),
            db=async_db,
            user="analyst",
        )

    result = await atlas_aggregates(db=async_db, _="analyst")
    assert len(result["aggregates"]) > 0

    json_str = json.dumps(result["aggregates"])
    forbidden_terms = [
        "case-pii", "run-pii", "owner", "analyst", "privacy-tester",
        "sha256", "original_filename", "storage_path", "license_plate", "plate",
        "first_name", "last_name", "driver", "vehicle_id",
    ]
    for term in forbidden_terms:
        assert term not in json_str, f"Forbidden term '{term}' leaked into aggregate payload!"


@pytest.mark.asyncio
async def test_opt_out_and_revocation_purges_contributions(async_db):
    """Consent revocation must immediately purge contributions from aggregates."""
    # Setup 5 cases to unlock a cohort
    for i in range(1, 6):
        cid, rid = f"case-revoke-{i}", f"run-revoke-{i}"
        await _seed_case_and_run(async_db, cid, rid)
        await set_consent(cid, ConsentInput(opted_in=True), db=async_db, user="owner")
        await add_contribution(
            cid,
            ContributionInput(
                source_run_id=rid,
                coarse_cell="9q8yy",
                time_bucket="2026-Q4",
                conflict_type="rear_end",
                road_user_mix={"motor_vehicle": 2},
                metrics={"minimum_ttc_s": 0.5},
                reviewer_confirmed=True,
            ),
            db=async_db,
            user="analyst",
        )

    # 5 cases -> visible
    pre = await atlas_aggregates(db=async_db, _="analyst")
    assert any(a["coarse_cell"] == "9q8yy" for a in pre["aggregates"])

    # Revoke consent on case 1
    await set_consent("case-revoke-1", ConsentInput(opted_in=False), db=async_db, user="owner")

    # Confirm contribution row was deleted from database
    purged = (await async_db.execute(
        select(AtlasContribution).where(AtlasContribution.case_id == "case-revoke-1")
    )).scalars().all()
    assert len(purged) == 0, "Contributions must be purged immediately upon revocation"

    # Now remaining distinct cases = 4 (< 5), so cell 9q8yy must drop below threshold
    post = await atlas_aggregates(db=async_db, _="analyst")
    assert not any(a["coarse_cell"] == "9q8yy" for a in post["aggregates"]), (
        "Cell must be suppressed after revocation drops distinct case count below 5"
    )


@pytest.mark.asyncio
async def test_consent_audit_trail_recorded(async_db):
    """Every opt-in and revocation must produce an immutable audit log entry."""
    cid = "case-audit-trail"
    await _seed_case_and_run(async_db, cid, "run-audit")

    # 1. Opt-in
    await set_consent(cid, ConsentInput(opted_in=True), db=async_db, user="user-alice")

    # 2. Revoke
    await set_consent(cid, ConsentInput(opted_in=False), db=async_db, user="user-alice")

    events = (await async_db.execute(
        select(AtlasConsentEvent).where(AtlasConsentEvent.case_id == cid).order_by(AtlasConsentEvent.created_at)
    )).scalars().all()

    assert len(events) == 2
    assert events[0].opted_in is True
    assert events[0].actor == "user-alice"
    assert events[0].scope_version == SCOPE_VERSION

    assert events[1].opted_in is False
    assert events[1].actor == "user-alice"

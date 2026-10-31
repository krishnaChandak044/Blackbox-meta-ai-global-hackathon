"""
Phase 2 tests — Perception & Geometry.

Covers:
  1. DLT homography with 4 known correspondences (identity-like config)
  2. Reprojection RMSE on a calibrated setup should be < 0.5 px
  3. ScaleUnavailable raised when calibration absent
  4. ScaleUnavailable raised when relative error > 10%
  5. Synthetic tracker produces tracks with correct structure
  6. Ground contact projection: world positions computed; sigma > 0
  7. Calibration API: add 4 anchors, fit, verify RMSE in response
  8. Tracks API: run returns 202, list returns tracks after job
  9. Human confirm / point correction audit trail
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from engine.geometry.homography import (
    PixelPoint,
    WorldPoint,
    estimate_homography,
    reprojection_errors_px,
)
from engine.geometry.scale import ScaleUnavailable, derive_scale, require_scale
from engine.tracking.ground_contact import ProjectionConfig, project_track
from engine.tracking.motion import MotionTracker
from engine.tracking.protocols import BoundingBox, ObjectLabel, Track, TrackPoint
from engine.tracking.synthetic import SyntheticTracker
from services.api.db import session as db_session
from services.api.db.models import Base
from services.api.main import app
from services.api.routes import media as media_routes
from services.worker.celery_app import app as celery_app

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def four_anchors():
    """
    Pixel → world correspondence for a known rectangular patch.
    Pixel origin top-left; world origin at patch corner.
    The patch is 10 m × 6 m in the world, occupying 200 × 120 px.
    """
    pixels = [
        PixelPoint(x=100, y=100),
        PixelPoint(x=300, y=100),
        PixelPoint(x=300, y=220),
        PixelPoint(x=100, y=220),
    ]
    world = [
        WorldPoint(x=0.0, y=0.0),
        WorldPoint(x=10.0, y=0.0),
        WorldPoint(x=10.0, y=6.0),
        WorldPoint(x=0.0, y=6.0),
    ]
    return pixels, world


@pytest_asyncio.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'phase2.db'}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "AsyncSessionLocal", factory)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SECRET_KEY", "a-test-secret-that-is-at-least-32-characters-long")
    monkeypatch.setenv("BLACKBOX_ACCESS_PASSWORD", "testpassword")
    monkeypatch.setattr(media_routes, "STORAGE_ROOT", tmp_path / "storage")
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Authenticate
        r = await ac.post("/api/v1/auth/session", json={"password": "testpassword"})
        assert r.status_code == 200, r.text
        yield ac
    await engine.dispose()


@pytest.fixture
def video_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "phase2.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x120:r=10:d=1",
            "-c:v",
            "mpeg4",
            "-y",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


# ── 1. DLT: 4 known correspondences ───────────────────────────────────────────


def test_homography_4_points_roundtrip(four_anchors):
    pixels, world = four_anchors
    result = estimate_homography(pixels, world)

    assert result.anchor_count == 4
    assert result.reprojection_rmse_px < 0.5, (
        f"RMSE {result.reprojection_rmse_px:.3f} too large for synthetic data"
    )

    # Every anchor should project back within 1 px
    for pp, wp in zip(pixels, world):
        projected = result.pixel_to_world(pp)
        dist = math.sqrt((projected.x - wp.x) ** 2 + (projected.y - wp.y) ** 2)
        assert dist < 0.1, f"World projection error too large: {dist:.4f} m"


# ── 2. Reprojection errors per anchor ─────────────────────────────────────────


def test_per_anchor_reprojection_errors(four_anchors):
    pixels, world = four_anchors
    result = estimate_homography(pixels, world)
    errors = reprojection_errors_px(result, pixels, world)

    assert len(errors) == 4
    assert all(e < 1.0 for e in errors), f"Outlier anchor errors: {errors}"


# ── 3. Fewer than 4 anchors raises ValueError ─────────────────────────────────


def test_homography_too_few_anchors():
    with pytest.raises(ValueError, match="At least 4"):
        estimate_homography(
            [PixelPoint(0, 0), PixelPoint(100, 0), PixelPoint(100, 100)],
            [WorldPoint(0, 0), WorldPoint(5, 0), WorldPoint(5, 5)],
        )


# ── 4. Scale: unavailable when not calibrated ─────────────────────────────────


def test_require_scale_raises_when_none():
    with pytest.raises(ScaleUnavailable) as exc_info:
        require_scale(None)
    assert exc_info.value.reason == "no_calibration"


# ── 5. Scale: relative error > 10% triggers refusal ──────────────────────────


def test_scale_refusal_on_large_error(four_anchors):
    pixels, world = four_anchors
    result = estimate_homography(pixels, world)
    # The actual distance between anchor 0 and 1 is 10 m, but we claim 100 m
    with pytest.raises(ScaleUnavailable) as exc_info:
        derive_scale(result, pixels[0], pixels[1], known_distance_m=100.0)
    assert exc_info.value.reason == "scale_error_too_large"


# ── 6. Scale: correct derivation ─────────────────────────────────────────────


def test_scale_correct_derivation(four_anchors):
    pixels, world = four_anchors
    result = estimate_homography(pixels, world)
    # Anchors 0→1 are 10 m apart in the world
    scale = derive_scale(result, pixels[0], pixels[1], known_distance_m=10.0)
    assert scale.relative_error < 0.05
    # pixels[0] → pixels[1] is 200 px → ~0.05 m/px
    assert abs(scale.metres_per_pixel - 0.05) < 0.005


# ── 7. Synthetic tracker structure ────────────────────────────────────────────


def test_synthetic_tracker_produces_valid_tracks(tmp_path):
    # Create a minimal dummy video file (just needs to exist; SyntheticTracker
    # falls back to defaults when OpenCV can't open it)
    dummy = tmp_path / "dummy.mp4"
    dummy.write_bytes(b"\x00" * 1024)

    tracker = SyntheticTracker(seed=42, n_vehicles=2, n_pedestrians=1)
    tracks = tracker.track(str(dummy), min_confidence=0.0)

    assert len(tracks) == 3
    for t in tracks:
        assert isinstance(t, Track)
        assert len(t.points) > 0
        # Points must be sorted by frame index
        frames = [p.frame_index for p in t.points]
        assert frames == sorted(frames)
        # Ground contact sanity
        for p in t.points:
            gx, gy = p.bbox.ground_contact_px
            assert gx == pytest.approx((p.bbox.x_min + p.bbox.x_max) / 2, abs=0.1)
            assert gy == pytest.approx(p.bbox.y_max, abs=0.1)


def test_motion_tracker_uses_video_pixels(tmp_path: Path):
    import cv2
    import numpy as np

    path = tmp_path / "moving.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    assert writer.isOpened()
    for frame in range(35):
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        if frame >= 10:
            x = 20 + frame * 3
            cv2.rectangle(image, (x, 110), (x + 45, 155), (255, 255, 255), -1)
        writer.write(image)
    writer.release()
    tracks = MotionTracker().track(str(path))
    assert tracks
    assert all(t.points[0].label.source_model == MotionTracker.MODEL_NAME for t in tracks)
    assert all(t.points[0].label.category == "unknown" for t in tracks)


# ── 8. Ground contact projection ──────────────────────────────────────────────


def test_ground_contact_projection(four_anchors, tmp_path):
    pixels, world = four_anchors
    hom = estimate_homography(pixels, world)
    scale_res = derive_scale(hom, pixels[0], pixels[1], 10.0)

    # Build a minimal synthetic track in the calibrated region
    track = Track(
        track_id="t1",
        points=[
            TrackPoint(
                frame_index=i,
                presentation_ts_s=i / 30.0,
                bbox=BoundingBox(x_min=100 + i * 2, y_min=150, x_max=140 + i * 2, y_max=200),
                label=ObjectLabel(category="vehicle", confidence=0.9, source_model="test"),
                detection_confidence=0.9,
            )
            for i in range(10)
        ],
        is_complete=True,
    )

    traj = project_track(track, hom, scale_res, ProjectionConfig())
    assert traj.speed_available
    assert len(traj.positions) == 10
    for gp in traj.positions:
        assert gp.sigma_m > 0, "1-sigma uncertainty must be positive"
        assert gp.world is not None


# ── 9. Calibration API: add anchors + fit ─────────────────────────────────────


@pytest.mark.asyncio
async def test_calibration_fit_via_api(client: AsyncClient, video_bytes: bytes):
    # Create case + media records so FK constraints pass
    case_r = await client.post(
        "/api/v1/cases/",
        json={
            "title": "Phase2 Cal Test",
            "consent_given": True,
        },
    )
    assert case_r.status_code == 201, case_r.text
    case_id = case_r.json()["id"]

    # We need a SourceMedia row — use the upload endpoint with a tiny dummy file
    import io

    dummy = io.BytesIO(video_bytes)
    media_r = await client.post(
        f"/api/v1/cases/{case_id}/media/",
        files={"file": ("test.mp4", dummy, "video/mp4")},
    )
    assert media_r.status_code == 201, media_r.text
    media_id = media_r.json()["id"]

    # Add 4 anchors
    anchor_payloads = [
        {"label": "A", "pixel_x": 100, "pixel_y": 100, "world_x": 0.0, "world_y": 0.0},
        {
            "label": "B",
            "pixel_x": 300,
            "pixel_y": 100,
            "world_x": 10.0,
            "world_y": 0.0,
            "known_distance_m": 6.0,
        },
        {
            "label": "C",
            "pixel_x": 300,
            "pixel_y": 220,
            "world_x": 10.0,
            "world_y": 6.0,
            "is_distance_ref_b": True,
        },
        {"label": "D", "pixel_x": 100, "pixel_y": 220, "world_x": 0.0, "world_y": 6.0},
    ]
    for p in anchor_payloads:
        r = await client.post(
            f"/api/v1/cases/{case_id}/media/{media_id}/calibration/anchors", json=p
        )
        assert r.status_code == 201, r.text

    # Fit
    fit_r = await client.post(f"/api/v1/cases/{case_id}/media/{media_id}/calibration/fit")
    assert fit_r.status_code == 201, fit_r.text
    fit = fit_r.json()

    assert fit["anchor_count"] == 4
    assert fit["reprojection_rmse_px"] < 1.0, f"RMSE too large: {fit['reprojection_rmse_px']}"
    assert len(fit["H"]) == 3 and len(fit["H"][0]) == 3
    assert len(fit["per_anchor_errors_px"]) == 4

    # Scale should be derived (anchors B + C form the reference pair)
    assert fit["scale_metres_per_pixel"] is not None
    assert fit["scale_relative_error"] < 0.05


# ── 10. Tracks API: run returns 202 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_tracks_run_queues_job(client: AsyncClient, monkeypatch, video_bytes: bytes):
    # Monkeypatch worker dispatch so the test doesn't need a real Celery broker
    dispatched = []

    def fake_delay(media_id, job_id):
        dispatched.append((media_id, job_id))

    case_r = await client.post(
        "/api/v1/cases/", json={"title": "Track Test", "consent_given": True}
    )
    case_id = case_r.json()["id"]
    import io

    media_r = await client.post(
        f"/api/v1/cases/{case_id}/media/",
        files={"file": ("clip.mp4", io.BytesIO(video_bytes), "video/mp4")},
    )
    media_id = media_r.json()["id"]

    monkeypatch.setattr(
        "services.worker.jobs.tracking.run_tracking_task",
        type("T", (), {"delay": staticmethod(fake_delay)})(),
    )

    run_r = await client.post(f"/api/v1/cases/{case_id}/media/{media_id}/tracks/run")
    assert run_r.status_code == 202, run_r.text
    assert "job_id" in run_r.json()
    assert len(dispatched) == 1

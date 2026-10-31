"""Phase 1 intake contract: private cases and preserved media."""

import hashlib
import subprocess
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.api.db import session as db_session
from services.api.db.models import Base, DerivedArtifact, JobStatus, ProcessingJob, SourceMedia
from services.api.main import app
from services.api.routes import media as media_routes
from services.worker.celery_app import app as celery_app


@pytest.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'phase1.db'}"
    engine = create_async_engine(db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "AsyncSessionLocal", factory)
    monkeypatch.setattr(media_routes, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SECRET_KEY", "a-test-secret-that-is-at-least-32-characters")
    monkeypatch.setenv("BLACKBOX_ACCESS_PASSWORD", "test-password")
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client, factory, tmp_path
    await engine.dispose()


@pytest.fixture
def sample_video(tmp_path: Path) -> bytes:
    path = tmp_path / "sample.mp4"
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


@pytest.mark.asyncio
async def test_private_intake_probe_integrity_and_delete(client, sample_video):
    http, factory, tmp_path = client
    assert (await http.get("/api/v1/cases/")).status_code == 401
    bad = await http.post("/api/v1/auth/session", json={"password": "bad"})
    assert bad.status_code == 401
    login = await http.post("/api/v1/auth/session", json={"password": "test-password"})
    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()

    case = (
        await http.post("/api/v1/cases/", json={"title": "Staged test", "consent_given": True})
    ).json()
    uploaded = await http.post(
        f"/api/v1/cases/{case['id']}/media/",
        files={"file": ("sample.mp4", sample_video, "video/mp4")},
    )
    if uploaded.status_code != 201:
        from sqlalchemy import select as _select

        async with factory() as _db:
            _jobs = (await _db.execute(_select(ProcessingJob))).scalars().all()
            print("JOB ERRORS", [j.error_message for j in _jobs])
    assert uploaded.status_code == 201, uploaded.text
    media = uploaded.json()
    assert media["sha256"] == hashlib.sha256(sample_video).hexdigest()
    assert media["status"] == "indexed"
    assert media["frame_count"] == 10
    assert media["codec"] == "mpeg4"
    assert media["is_variable_framerate"] is False
    integrity = (await http.get(f"/api/v1/cases/{case['id']}/media/{media['id']}/integrity")).json()
    assert integrity["intact"] is True

    async with factory() as db:
        stored = await db.get(SourceMedia, media["id"])
        original_path = Path(stored.storage_path)
        assert original_path.read_bytes() == sample_video
        artifacts = (await db.execute(select(DerivedArtifact))).scalars().all()
        assert len(artifacts) == 1
        index_path = Path(artifacts[0].storage_path)
        assert index_path.exists()
        jobs = (await db.execute(select(ProcessingJob))).scalars().all()
        assert len(jobs) == 1 and jobs[0].status == JobStatus.DONE

    downloaded = await http.get(f"/api/v1/cases/{case['id']}/media/{media['id']}/original")
    assert downloaded.status_code == 200 and downloaded.content == sample_video
    original_path.write_bytes(b"tampered")
    bad_integrity = (
        await http.get(f"/api/v1/cases/{case['id']}/media/{media['id']}/integrity")
    ).json()
    assert bad_integrity["intact"] is False
    assert (
        await http.get(f"/api/v1/cases/{case['id']}/media/{media['id']}/original")
    ).status_code == 409
    original_path.write_bytes(sample_video)

    deleted = await http.delete(f"/api/v1/cases/{case['id']}")
    assert deleted.status_code == 204
    assert not original_path.exists()
    assert not index_path.exists()


@pytest.mark.asyncio
async def test_upload_limit_and_mime_rejected(client, sample_video):
    http, _, _ = client
    await http.post("/api/v1/auth/session", json={"password": "test-password"})
    case_id = (await http.post("/api/v1/cases/", json={"title": "Limit test"})).json()["id"]
    wrong = await http.post(
        f"/api/v1/cases/{case_id}/media/",
        files={"file": ("notes.txt", b"not video", "text/plain")},
    )
    assert wrong.status_code == 415
    for _ in range(3):
        result = await http.post(
            f"/api/v1/cases/{case_id}/media/",
            files={"file": ("sample.mp4", sample_video, "video/mp4")},
        )
        assert result.status_code == 201, result.text
    fourth = await http.post(
        f"/api/v1/cases/{case_id}/media/",
        files={"file": ("sample.mp4", sample_video, "video/mp4")},
    )
    assert fourth.status_code == 400

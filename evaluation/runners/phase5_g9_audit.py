"""Audit a freshly completed Phase 5 staged-upload-to-export smoke run."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from services.api.db.models import (
    Case,
    DynamicsRun,
    EvidenceNeed,
    ExportRecord,
    HomographyFit,
    JobStage,
    JobStatus,
    ProcessingJob,
    ProcessingLog,
    SourceMedia,
)
from services.api.db.revision import canonical_json


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def audit(database_url: str, storage_root: Path, case_id: str, export_id: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    root = storage_root.resolve()
    try:
        with Session(engine) as db:
            case = db.get(Case, case_id)
            record = db.get(ExportRecord, export_id)
            if case is None or record is None or record.case_id != case_id:
                raise ValueError("The requested case/export pair does not exist")
            media = db.execute(select(SourceMedia).where(SourceMedia.case_id == case_id)).scalars().all()
            jobs = db.execute(select(ProcessingJob).where(
                ProcessingJob.case_id == case_id,
                ProcessingJob.stage == JobStage.PROBE,
            )).scalars().all()
            logs = db.execute(select(ProcessingLog).where(
                ProcessingLog.case_id == case_id,
            )).scalars().all()
            needs = db.execute(select(EvidenceNeed).where(EvidenceNeed.case_id == case_id)).scalars().all()
            fits = db.execute(select(HomographyFit).where(HomographyFit.case_id == case_id)).scalars().all()
            dynamics = db.execute(select(DynamicsRun).where(DynamicsRun.case_id == case_id)).scalars().all()
            if record.status != "complete" or not record.json_path or not record.pdf_path:
                raise ValueError(f"Export is not complete: {record.status}")
            json_path, pdf_path = Path(record.json_path), Path(record.pdf_path)
            if not json_path.is_file() or not pdf_path.is_file():
                raise ValueError("One or more export artifacts are missing")
            manifest = json.loads(json_path.read_text(encoding="utf-8"))
            unsigned = dict(manifest)
            manifest_digest = unsigned.pop("manifest_sha256", None)
            verified_manifest_digest = hashlib.sha256(canonical_json(unsigned)).hexdigest()
            source_checks = []
            for row in media:
                source_path = Path(row.storage_path).resolve()
                actual = sha256_file(source_path) if root in source_path.parents and source_path.is_file() else None
                source_checks.append({"media_id": row.id, "intact": actual == row.sha256,
                    "indexed": row.status.value == "indexed", "sha256": actual})
            upload_jobs_done = any(job.status == JobStatus.DONE for job in jobs)
            processing_history_present = bool(logs)
            artifacts_confined = root in json_path.resolve().parents and root in pdf_path.resolve().parents
            checks = {
                "fresh_case_has_source_media": bool(media),
                "source_hashes_match_intake": all(item["intact"] for item in source_checks),
                "media_probe_job_completed": upload_jobs_done,
                "processing_history_present": processing_history_present,
                "export_complete": record.status == "complete",
                "json_artifact_hash_valid": sha256_file(json_path) == record.json_sha256,
                "pdf_artifact_hash_valid": sha256_file(pdf_path) == record.pdf_sha256,
                "manifest_digest_valid": manifest_digest == record.manifest_sha256 == verified_manifest_digest,
                "manifest_matches_requested_revision": manifest.get("case_revision_hash") == record.case_revision_hash,
                "missing_calibration_is_explicit_fallback": not fits and not dynamics,
                "radar_has_metric_scale_evidence_need": any(row.need_key == "measure_scene_distance" for row in needs),
                "artifacts_confined_to_storage_root": artifacts_confined,
            }
            if not all(checks.values()):
                raise ValueError(f"G9 audit failed: {[name for name, passed in checks.items() if not passed]}")
            return {
                "gate": "G9-fresh-upload-to-export",
                "status": "PARTIAL_PASS",
                "executed_at_utc": datetime.now(timezone.utc).isoformat(),
                "environment": "isolated temporary SQLite database with Phase 5 Alembic migrations applied",
                "case_id": case_id,
                "export_id": export_id,
                "source_media_count": len(media),
                "source_checks": source_checks,
                "processing_job_count": len(jobs),
                "processing_history_count": len(logs),
                "case_revision_hash": record.case_revision_hash,
                "manifest_sha256": record.manifest_sha256,
                "pdf_sha256": record.pdf_sha256,
                "json_sha256": record.json_sha256,
                "checks": checks,
                "limits": [
                    "The uploaded media was generated locally with FFmpeg and is synthetic, not real crash evidence.",
                    "No SAM tracking credentials were configured, so the app correctly exercised the missing-calibration path; no calibrated tracks or dynamics were produced.",
                    "A browser synthetic fixture rendered populated observed/fitted/counterfactual/rival paths; production case rendering and orbit/pan pointer behavior remain unverified.",
                    "This local SQLite migration run verifies the migration chain against a legacy-schema fixture; the unrelated local PostgreSQL instance could not be used.",
                ],
            }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--export-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("evaluation/scorecards/phase5_g9_smoke_2026-11-01.md"))
    args = parser.parse_args()
    result = audit(args.database_url, args.storage_root, args.case_id, args.export_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("# Phase 5 G9 smoke scorecard\n\n" + "\n".join(
        f"- **{key.replace('_', ' ')}:** {json.dumps(value, ensure_ascii=False)}"
        for key, value in result.items()) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"scorecard: {args.output}")


if __name__ == "__main__":
    main()

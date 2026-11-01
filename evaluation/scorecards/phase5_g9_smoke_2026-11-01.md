# Phase 5 G9 smoke scorecard

- **gate:** "G9-fresh-upload-to-export"
- **status:** "PARTIAL_PASS"
- **executed at utc:** "2026-11-01T12:19:59.129267+00:00"
- **environment:** "isolated temporary SQLite database with Phase 5 Alembic migrations applied"
- **case id:** "28887e90-2660-4beb-9a63-fca393f00368"
- **export id:** "a681bce4-4914-47b8-b86a-d34f487d6621"
- **source media count:** 1
- **source checks:** [{"media_id": "f0689e34-f754-448a-a9cd-bcd788ec990b", "intact": true, "indexed": true, "sha256": "bb65f29686f094cdfd7058bc20a5da5be77451ec40b38882735c9a73a892fc08"}]
- **processing job count:** 1
- **processing history count:** 3
- **case revision hash:** "1d1fe12f80c0829530f9ce7907b11600fa60843b87978bbadc6999ff45a22713"
- **manifest sha256:** "7de17c519c013c7b04dd4639315b0f3850e3e14e8798c6777d4ac99180ba90f8"
- **pdf sha256:** "3a2782bb23ec2de83c8843b173b5ac087e1a29f74be13e39df20c0dcec2c2e54"
- **json sha256:** "f7dfa0a7dbf96d68a288662b4d57a1c468d57eca857f146c7e704606546648fd"
- **checks:** {"fresh_case_has_source_media": true, "source_hashes_match_intake": true, "media_probe_job_completed": true, "processing_history_present": true, "export_complete": true, "json_artifact_hash_valid": true, "pdf_artifact_hash_valid": true, "manifest_digest_valid": true, "manifest_matches_requested_revision": true, "missing_calibration_is_explicit_fallback": true, "radar_has_metric_scale_evidence_need": true, "artifacts_confined_to_storage_root": true}
- **limits:** ["The uploaded media was generated locally with FFmpeg and is synthetic, not real crash evidence.", "No SAM tracking credentials were configured, so the app correctly exercised the missing-calibration path; no calibrated tracks or dynamics were produced.", "A browser synthetic fixture rendered populated observed/fitted/counterfactual/rival paths; production case rendering and orbit/pan pointer behavior remain unverified.", "This local SQLite migration run verifies the migration chain against a legacy-schema fixture; the unrelated local PostgreSQL instance could not be used."]

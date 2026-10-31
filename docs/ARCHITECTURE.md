# Technical architecture

## System boundary

Blackbox has five layers: source-preserving case storage; media and perception processing; deterministic geometry and physics; claim and scenario analysis; and human-facing review/export. The numerical engine is the authority for calculations. Language models extract and explain typed data but cannot create observations, citations, or numerical verdicts.

## Pipeline

```text
Upload -> original store + SHA-256 + media metadata
       -> derived playback copies + frame/timestamp index
       -> SAM tracking + human track corrections
       -> clip synchronization + camera calibration
       -> measured 2D trajectories + uncertainty
       -> dynamics fit + identifiability analysis
       -> counterfactual and rival-hypothesis runs
       -> 3D view, claim ledger, evidence rescue, export

Audio -> transcription -> editable atomic claims
                       -> independent check against video-derived events
```

Each stage receives an immutable input manifest and emits an immutable output manifest. Jobs are retryable by content hash. A stage failure cannot overwrite original media or a previous valid result.

## Suggested components

- **Web UI:** case intake, synchronized clip viewer, timeline, calibration editor, claim ledger, 2D/3D workbench, evidence radar, export.
- **API:** authentication, cases, media upload, jobs, review actions, exports. Use scoped URLs and server-side model credentials.
- **Object storage:** original and derived media in separate namespaces; original bytes never transcoded in place.
- **Metadata store:** case records, manifests, tracks, measurements, findings, reviewer actions, job status. SQLite is adequate for a local demo; use a durable managed database if hosted.
- **Worker queue:** video probing, thumbnailing, model calls, geometry fitting, sampling, report generation. Jobs are idempotent and resumable.
- **Perception adapter:** SAM 3.1 request/response parsing, confidence, mask lineage, tracking review.
- **Numerical engine:** camera model, homography, tracks, event detection, dynamics, uncertainty, scenario simulation, identifiability and rival search.
- **Language adapter:** transcription, structured atomic-claim extraction, explanation only from typed tool results.
- **3D renderer:** WebGL/Three.js or equivalent, driven entirely by typed trajectories. Generic meshes are the baseline. SAM 3D meshes are optional illustrative assets.

## Geometry rules

Store source frame presentation timestamps, not just `frame_index / nominal_fps`. Use ground-contact points for vehicle-to-ground mapping. Calibrate a fixed camera from multiple reviewed anchors; record anchor positions, units, source frames, reprojection residuals, and a distribution over plausible transforms. Detect or flag moving camera, zoom, lens distortion, and weak perspective. Without reliable scale, suppress absolute speed and stopping-distance results.

## Inverse physics rules

Fit a forward motion model to measured trajectories. Keep observation error, calibration error, timing offset, and prior uncertainty separate. Compare posterior predictive tracks with actual tracks. Report parameter correlations. Treat visible braking onset as potentially estimable; do not infer driver perception or reaction time without an independent observation. Run counterfactuals over plausible parameter samples and report conditional scenario fractions with sensitivity analysis.

## Model contracts

SAM emits candidate masks/tracks, not truth. Muse Voice emits editable transcripts, not truth. Muse Spark emits schema-valid claims and explanations, not physical measurements. The numerical engine emits measurements and model results with units and source lineage. Reviewer corrections are versioned and can be replayed. All model IDs, prompts/configurations, and output hashes are recorded.

## Reproducibility

Every numerical run records engine commit/version, input manifest hash, model configuration, random seed, units, and output hash. A standalone replay command should regenerate results from a case export where licenses and privacy permit. The report must say when a result depends on a hosted model and cannot be reproduced offline.

## Failure behavior

A model timeout leaves the case intact and marks that stage incomplete. A failed calibration blocks metric outputs but permits frame-cited timeline and statements about directly visible events. Failed speech recognition permits manual transcript entry. Failed SAM 3D falls back to generic meshes. Missing audio invokes visual or manual clip alignment. No fallback silently upgrades confidence.

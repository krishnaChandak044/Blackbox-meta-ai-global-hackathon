# Data and API contracts

## Provenance classes

Every finding has one primary class: `OBSERVED` (directly visible or audible in a source), `MEASURED` (calculated from source and calibration), `ASSUMED` (user, prior, or default input), `SIMULATED` (what-if result), or `UNKNOWN`. A finding may list dependencies from other classes. UI color alone is insufficient; show text labels.

## Required entities

- `Case`: ID, owner, title, jurisdiction if supplied, consent flags, created time, retention settings.
- `SourceMedia`: ID, original filename, MIME/codec, byte length, SHA-256, acquisition notes, upload time, device clock metadata, storage reference.
- `DerivedArtifact`: ID, parent IDs/hashes, transformation, tool version, parameters, output hash, creation time.
- `FrameReference`: source media ID, presentation timestamp in microseconds, frame index, optional region/mask ID.
- `Camera`: source media ID, fixed/moving/unknown, intrinsics/distortion if known, pose and uncertainty.
- `CalibrationAnchor`: source frame, image coordinates, world coordinates, unit, measurement origin, reviewer status.
- `TrackObservation`: frame reference, object ID, class, mask/box, ground-contact point, confidence, review state.
- `TimeAlignment`: clip pair, offset distribution, alignment method, anchor events, reviewer status.
- `Event`: typed observation, participant IDs, time interval, geometry, source references.
- `Statement`: audio/text source, language, transcript versions, speaker label when consented.
- `AtomicClaim`: exact text span, normalized claim, subjects, event relation, ambiguity flags.
- `Finding`: claim ID, `supported|contradicted|undeterminable`, test rule, citations, uncertainty, reviewer state.
- `ModelRun`: input hashes, algorithm/version, priors, calibration, seed, fit diagnostics, warnings.
- `Intervention`: parameter changed, original value, new value, units, rationale.
- `CounterfactualResult`: model run, intervention, scenario outcomes, sensitivity, limitations.
- `AnswerabilityCertificate`: question, required observations, available observations, assumptions, status (`measurable|conditional|not_identifiable`), sensitivity.
- `RivalHypothesis`: alternate parameter set, observation fit, difference from primary fit, disambiguating evidence.
- `ReviewerAction`: actor, time, target, old value, new value, reason.

## Units and time

Use SI units internally: metres, seconds, metres/second, metres/second squared, radians. Show km/h only as a derived display value. Persist timestamps as integer microseconds from each clip's presentation timeline; store UTC wall-clock times separately. Never merge device clocks without an explicit offset and uncertainty. World coordinates are right-handed with ground `z=0`; store origin and axis orientation.

## Invariants

1. Original media is immutable; a hash mismatch fails verification.
2. A cited frame must exist in the named source and presentation-time index.
3. A `MEASURED` finding must list calibration and source observations.
4. A `SIMULATED` finding must list model run and intervention; it cannot be cited as a historical observation.
5. A `contradicted` claim requires an explicit test rule and source evidence independent of that statement.
6. A numeric value has units, confidence/uncertainty method, and a scope flag.
7. Reviewer changes append a new version; they never erase a prior finding.

## Minimal API sketch

```text
POST   /cases
POST   /cases/{id}/media                 -> upload session
GET    /cases/{id}/media/{mediaId}       -> metadata and integrity status
POST   /cases/{id}/analysis              -> queued job ID
GET    /jobs/{jobId}                     -> stage, progress, errors
GET    /cases/{id}/timeline              -> events with frame references
POST   /cases/{id}/calibration           -> versioned reviewed anchors
POST   /cases/{id}/statements            -> audio or text
GET    /cases/{id}/claims                -> atomic claims and findings
POST   /cases/{id}/counterfactuals       -> intervention and model run
POST   /cases/{id}/rivals                -> bounded alternate search
GET    /cases/{id}/answerability         -> certificates
GET    /cases/{id}/evidence-needs        -> ranked missing evidence
POST   /cases/{id}/review-actions        -> versioned corrections
POST   /cases/{id}/exports               -> review package job
```

All endpoints are authenticated, case scoped, and schema validated. Errors distinguish unsupported media, insufficient evidence, model failure, and permission failure.

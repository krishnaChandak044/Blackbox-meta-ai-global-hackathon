# Build plan and integration gates

This is an implementation order for the full PRD, not a feature reduction. Each stage produces a reviewable artifact and a passing gate before downstream work relies on it.

## Workstreams

| Workstream | Owns | Contract |
| --- | --- | --- |
| Evidence foundation | Storage, hashing, metadata, provenance, exports | Immutable originals and reproducible manifests |
| Perception and geometry | SAM adapter, tracking review, sync, calibration | Timestamped observations and calibrated coordinates |
| Physics and uncertainty | Motion model, inference, sensitivity, counterfactuals, rival search | Typed numerical results with assumptions and fit diagnostics |
| Language and claims | Transcription, atomic claims, independent checker | Frame-cited, three-way findings |
| Experience | UI, synchronized 2D/3D, radar, atlas | No visual claim stronger than its underlying data |
| Validation | Datasets, independent annotations, metrics, demo rehearsal | Results separated from targets and fixtures |

## Dependency sequence

1. Create repository, environment setup, typed schemas, sample case, and CI checks.
2. Build immutable intake, content hashes, frame indexing, and processing manifest.
3. Add fixed-camera SAM tracking with a human correction interface.
4. Add clip synchronization and ground-plane calibration with refusal rules.
5. Build 2D event timeline and numerical engine; verify against synthetic truth.
6. Add voice transcription, atomic claim extraction, and independent checks.
7. Add Bayesian/likelihood-based dynamics fit, parameter correlations, and identifiability certificates.
8. Add intervention simulator, sensitivity analysis, and rival-hypothesis search.
9. Drive an orbitable 3D scene from the same engine; add optional SAM 3D meshes.
10. Add Evidence Rescue Radar and preservation-request draft.
11. Add consented Prevention Atlas and deduplication for multiple incidents.
12. Build Phase 5: evidence-linked 3D, Evidence Rescue Radar, consented Prevention Atlas, and immutable review export.
13. Run held-out, controlled-real, safety, privacy, and fresh-upload-to-export evaluations; ship report and demo.

## Integration gates

- **G1, source:** original re-download hash equals upload hash; no in-place transcoding.
- **G2, perception:** tracked ground-contact points have source frames and error measurements.
- **G3, geometry:** known-distance scene yields a calibrated interval; uncalibrated scene yields no absolute speed.
- **G4, claims:** claim checker produces supported, contradicted, undeterminable on predeclared cases and never uses testimony in the fit.
- **G5, physics:** simulated ground truth is recovered within stated intervals across a held-out set.
- **G6, what-if:** same input/seed reproduces results; changing an assumption changes the sensitivity display.
- **G7, 3D:** object positions match 2D engine and all unseen viewpoints carry a visible label.
- **G8, differentiation:** missing-evidence suggestion adds value; rival hypothesis is found and disambiguated.
- **G9, product:** fresh upload reaches export with no hidden intervention and readable limitations.

## Phase 4 implementation plan — physics, simulation, and rivals

### Purpose and non-goals

Phase 4 answers two bounded questions: what motion histories are consistent with the calibrated tracks, and how do explicitly selected assumptions change a simulated outcome? It does not determine legal fault, driver intent, reaction time, or a unique real-world crash narrative. Every result is an analysis of supplied observations under versioned assumptions.

The fit consumes track observations and calibration/probe metadata only. Phase 3 statements must never enter the fitting or optimization objective; they can be compared with the finished, versioned result afterward.

### Inputs and eligibility

The worker must snapshot and record the exact input IDs, content hashes/versions, parameters, software revision, and random seed used for a run. Inputs are:

- One explicitly selected vehicle track, with frame index, presentation timestamp, ground-contact point, and tracker localization uncertainty per observation.
- A valid ground-plane mapping and scale in SI units, including homography reprojection RMSE and scale relative error.
- Frame timing and variable-frame-rate metadata from the Phase 1 probe.
- A declared motion model and parameter bounds. Initial model: piecewise constant acceleration in 2D over a short, user-selected interval; do not silently assume a level road, constant friction, or no steering.

Reject or return `not_identifiable` when the track is unconfirmed/ambiguous, calibration is absent or invalid, timestamps are non-monotonic/unavailable, units are unknown, the interval lacks enough observations, or required uncertainty metadata is missing. Never turn image pixels directly into absolute speed. Missing observations must not be filled in as if measured; any smoothing/interpolation must be marked as model output.

### Dynamics inference and output contract

Implement a framework-free numerical core in `engine/dynamics/` using NumPy and SciPy only. Use a deterministic likelihood/least-squares fit with explicit parameter bounds and robust residual handling. A Bayesian posterior is optional only after priors and posterior diagnostics are recorded; do not call a point fit “Bayesian.” The fit must expose residuals, fit quality, parameter correlations or profile sensitivity, convergence status, and model version.

Return typed, versioned results containing:

- Smoothed positions and velocity vectors with timestamp/frame provenance and uncertainty intervals.
- Braking-onset interval only when the observed trajectory has a supported deceleration change point; otherwise `not_identifiable` or `conditional`.
- Deceleration interval only when the selected model is sufficiently constrained and passes fit diagnostics.
- The five uncertainty contributions separately: pixel localization, homography reprojection, scale calibration, frame timestamp, and model assumptions. Record each distribution/range, source metadata, and propagation method.
- An identifiability certificate per quantity: `measurable`, `conditional`, or `not_identifiable`, with machine-readable reasons, assumptions, evidence references, and the additional observation that could improve it.

### Uncertainty protocol

Use seeded Monte Carlo propagation over documented error distributions. Keep the five sources separately inspectable, then report their combined effect and interactions. State whether an interval is a percentile range, a confidence interval, or only an illustrative range. Do not label an interval “95% CI” until repeated held-out evaluations demonstrate the corresponding empirical coverage. If a source distribution is unknown, expose that limitation and use a broad declared bound or abstain; do not invent precision.

### Counterfactual simulator

The simulator consumes an immutable dynamics result plus explicit user-selected interventions, such as braking onset shift or entry-speed change. It must not mutate the fitted baseline or imply the intervention happened. Show baseline observations, fitted trajectory, and simulated counterfactual as distinct layers. Every output is labeled `ILLUSTRATIVE — model scenario, not observed fact` in the UI and exports.

Document model assumptions alongside each result (initially: selected coordinate plane, interval, acceleration model, and any assumed road/steering/friction parameters). Define allowable slider bounds from observed support and configured limits; visibly flag extrapolation outside the observed range. Sensitivity output must state its perturbation ranges and metric, and identify which additional measurement could reduce uncertainty rather than claim that a control is causal truth.

### Bounded rival-hypothesis search

Implement a deterministic, bounded parameter search. Version and record the dimensions searched, bounds, grid/sampling strategy, seed, objective, residual metric, acceptance threshold, and number of candidates evaluated. Return ranked alternatives only when they are materially different from the primary fit and remain within the predeclared residual tolerance. If none qualify, say “no acceptable rival found in the searched bounds”; never imply that all possible alternatives were ruled out.

Second-camera evidence may disambiguate a rival only when clips are synchronized, calibrated into a compatible frame, and include the relevant observed interval. Report the specific residual/evidence change that rejects a rival. If alignment or calibration is inadequate, retain the rival as unresolved.

### API, jobs, storage, and invalidation

- `POST /cases/{case_id}/media/{media_id}/dynamics` queues an inference job and returns a job ID; `GET .../dynamics` returns the latest immutable run and status.
- `POST /cases/{case_id}/media/{media_id}/simulate` validates the baseline run ID and intervention bounds, then returns a versioned illustrative result.
- `GET /cases/{case_id}/media/{media_id}/rivals` returns the bounded search manifest and ranked candidates, including an explicit empty-search outcome.
- Every request and response has a Pydantic/OpenAPI contract, units, nullable fields, enums, validation errors, and provenance. Jobs surface queued/running/done/failed states and error details.
- Persist immutable run records and link outputs to track IDs, track/calibration versions, media hashes, parameter/config hashes, model version, and seed. A changed track, calibration, media index, or model configuration makes dependent outputs stale; never silently reuse them.
- Add Alembic migrations for all new result/job tables or fields. Deployments run migrations explicitly; `Base.metadata.create_all()` is not a migration strategy for existing databases.

### Frontend and report requirements

Build report panels at `/cases/[id]/media/[id]/dynamics`, `/simulate`, and `/rivals`. Show observed points separately from fitted and simulated paths. Every numeric quantity displays units, interval type, interval bounds, and certificate status; e.g. `speed: 52–68 km/h (illustrative 95% range under listed assumptions)` until coverage is validated. Never render a bare estimate as established fact. Include an assumptions/provenance drawer and links to source frames. Clearly badge simulated paths and synthetic fixtures as `ILLUSTRATIVE` in every chart, card, export, and screenshot.

### Implementation status and migration note

The Phase 4 implementation is on branch `feature/phase-4-physics`. The repository currently initializes tables with `Base.metadata.create_all()` and its Phase 3 Alembic revision is a partial schema patch with no base-schema parent. The Phase 4 migration is consequently additive for an existing app schema, but is not a standalone clean-install schema history. Production rollout must first establish a baseline migration and remove schema creation from API startup. Existing `track_points` receive a nullable pixel-localisation uncertainty column; old rows remain NULL and must be regenerated by rerunning tracking before metric inference.

G5, G6, and G8 are not considered passed until the evaluation artifacts described below are run and recorded. The implementation alone does not establish validated forensic accuracy.

### Acceptance gates for Phase 4

- **G5 — recovery and interval coverage:** use a preregistered suite of seeded synthetic trajectories spanning speeds, braking profiles, noise, missing frames, and the five uncertainty sources. Keep a held-out scenario set. Report bias/error and empirical interval coverage with sample counts. Pass only if ground truth falls inside the claimed interval at the claimed rate within a predefined tolerance, and the result abstains on deliberately unidentifiable cases. One successful clip is not sufficient.
- **G6 — reproducibility:** same canonical input hashes, parameters, software/model version, and seed produce identical serialized outputs on the supported runtime. Record tolerances if floating-point determinism across platforms is not guaranteed. Changing one declared assumption changes the expected output and sensitivity record; unrelated metadata does not.
- **G8 — rival discovery and disambiguation:** include a predeclared planted rival that fits a single view within the acceptance residual. Verify search finds it within declared bounds. Add a synchronized, calibrated second view with a predeclared distinguishing observation; verify the rival residual crosses the rejection threshold for that documented reason. Also test a case where the second view is insufficient and the system keeps the rival unresolved.

Do not mark Phase 4 complete until G5, G6, and G8 have recorded evaluation artifacts, the migration and API contracts are present, and the UI labels are visible in the export—not merely in development logs.

## Phase 5 implementation plan — 3D replay, rescue radar, atlas, and export

### Backend implementation status (2026-11-01)


Verification on 2026-11-01: the Phase 5 migration chain upgraded an isolated legacy-schema SQLite fixture to `20261101_phase5_backend` (head). G7 backend contract scoring passed 100 observed samples (300 coordinate components) at zero error, with provenance and illustrative-label checks passing. A synthetic UI fixture rendered observed, fitted, counterfactual, and rival paths in the browser; the persistent illustrative label and unknown-camera state were visible, and timeline/zoom/layer/reset controls responded. This does not yet verify production case tracks, WebGL fallback, source-frame jump, or orbit/pan pointer behavior. G9 reached a completed PDF/JSON export from a fresh synthetic upload through the visible UI; all 12 hash, history, manifest, fallback, and storage-confinement audit checks passed. The G9 scorecard remains `PARTIAL_PASS`: no SAM credentials were configured, so no calibrated tracks or dynamics were produced, and the required failure-recovery repeat was not run. The frontend build/type checks and backend static checks passed; lint reported only the pre-existing React hook warning in the transcript page. These results do not establish production readiness, privacy review, or a production database migration baseline.

### Purpose and completion boundary

Phase 5 turns the versioned outputs from Phases 1–4 into a reviewable case package. It adds an orbitable, time-synchronized 3D explanation; a ranked request for missing evidence; an opt-in, privacy-protected multi-case prevention view; and a self-contained PDF plus JSON export. It does not infer unseen facts from a 3D mesh, identify nearby camera owners, send preservation requests, publish personal case information, or turn modeled junction outcomes into engineering advice.

The complete user flow is: **fresh upload → integrity and processing record → reviewed/calibrated tracks → dynamics and claim results where supported → 2D/3D replay → optional evidence collection actions → export with traceable lineage and limitations**. A step that is not applicable or cannot be completed must end in a visible refusal/incomplete state with a reason; the demo must not rely on hidden pre-seeding, manual database edits, or unreported cached outputs.

### Phase 5A — shared scene contract and 3D replay (G7)

#### Data contract

Create one versioned, renderer-neutral scene payload in the API contract layer. Minimum fields:

- `scene_id`, `schema_version`, `case_id`, `generated_at`, and scene provenance/status (`observed`, `measured`, `assumed`, `simulated`, `unknown`).
- Coordinate metadata: right-handed axes, SI metres, ground plane `z=0`, origin and orientation source, and the exact calibration/transform IDs. Transform 2D engine coordinates into this frame in one documented adapter; the browser does not redo camera calibration or physics.
- Per object: stable track ID, class, geometry source (`generic_proxy` or optional generated asset), timestamped `x/y/z` positions, orientation where supported, source frame references, observed/interpolated status, and position/orientation uncertainty.
- Per camera: source media ID, calibrated pose and uncertainty when known, intrinsics/field of view when supported, and an explicit `unknown` state where pose is not recoverable. Frustums are explanatory coverage approximations, not proof that every pixel is visible.
- Per path: path type (`observed_track`, `fitted`, `counterfactual`, or `rival`), source run/intervention IDs, valid time range, uncertainty width, and mandatory illustrative state for generated/simulated content.
- Per event: presentation timestamp, source frame references, event type, and links to relevant claims/findings.

Coordinates are sampled/interpolated only for display between engine samples; those display samples must retain an `interpolated_for_rendering` marker and may not be re-used as observations or fed back to inference. If height, orientation, camera pose, or scale is unavailable, render the corresponding uncertainty/unknown state rather than fabricate precision.

#### Viewer and interaction

- Implement the 3D view in a client-only React Three Fiber/Three.js component; use accessible controls and provide a synchronized top-down 2D fallback when WebGL is unavailable.
- Use generic parameterized meshes as the reliable baseline. An optional SAM 3D asset can change appearance only; it cannot alter engine positions, collision calculations, event claims, or fit results. Asset failure/licensing/runtime restrictions fall back to generic meshes.
- Provide orbit, pan, zoom, reset, timestamp scrub/play-pause, object selection, and toggles for source-camera frustums, measured/fitted paths, uncertainty tubes, counterfactual ghosts, and rival alternatives. Keep the selected timestamp synchronized with source video/frame views and the 2D canvas.
- Show paths distinctly: observed samples, fitted model, and each simulated/rival path use different text labels and visual encodings. Do not rely on color alone. Any synthetic viewpoint, geometry, or scenario displays a persistent `ILLUSTRATIVE — NOT SOURCE FOOTAGE` label while visible, including screenshots and exported renderings.
- Clicking an observed sample/event opens its original media and exact frame. Clicking a fitted or simulated sample opens the calculation/run and assumptions, not a fabricated source frame.
- Show uncertainty as a tube/envelope only where a supported numeric interval exists. Otherwise display `uncertainty unavailable` or an explicit conditional/unknown state. Never visually imply the tube is a probability region unless its coverage is validated.

#### G7 acceptance checks

1. For every scene fixture, compare 3D adapter world positions against the exact 2D engine inputs at a preregistered set of timestamps. Test origin/axis transforms, unit conversions, missing timestamps, and the first/last valid samples. Set a numeric tolerance in metres before running; record max error, RMS error, sample count, and versions. The target is <= 1e-6 m for pure coordinate-preserving adapters; if an intentional transform/interpolation is under test, declare an appropriate tolerance in the fixture before execution.
2. Assert that observed tracks remain byte/value-equivalent to their source engine samples and that mesh geometry cannot change physical data.
3. Browser acceptance: orbit/scrub, source-frame jump, 2D fallback, and every label work with generic meshes; repeat with the optional mesh disabled and with WebGL unavailable.
4. Capture UI states for observed-only, fitted, counterfactual, rival, unknown camera pose, and synthetic viewpoint. Automated DOM checks and a manual visual review must confirm a persistent visible label for each generated/simulated view.

### Phase 5B — Evidence Rescue Radar

#### Inputs and ranking

Create a deterministic evidence-needs service that consumes typed answerability/identifiability certificates, unresolved rival manifests, occlusion/source-coverage intervals, case media inventory, user-entered scene facts, and optional verified retention deadlines. It emits candidate collection actions such as: obtain an original export from an already-known clip; collect a specific time window from a user-identified camera; measure a known scene distance; obtain a traffic-signal log; or request expert review.

Each candidate records: `need_id`, question/quantity it may resolve, required time interval/scene location, evidence type, supporting dependencies, predicted uncertainty change with metric and assumptions, estimated effort/access friction, privacy cost, urgency/deadline source, rank explanation, and confidence/unknown flags. Rank by a documented deterministic utility (expected uncertainty reduction per effort, adjusted by urgency and privacy cost); do not ask an LLM to invent an evidence source or its expected effect. Missing or unsupported inputs must lower confidence or produce `unknown`, never a fabricated deadline, owner, or guaranteed uncertainty reduction.

Urgency countdown is shown only when a human verifies and records the source, date/time, timezone, and deadline basis. Otherwise show `retention deadline unknown`. A nearby business, map pin, or inferred camera view is only a possible source and must never be represented as having CCTV or a known owner without human verification. The feature drafts a request for a human to review; it never sends a message automatically. Persist the candidate snapshot, ranking inputs, reviewer decision, and status transitions (`suggested`, `verified_source`, `drafted`, `requested_by_user`, `received`, `unavailable`, `refused`).

#### Radar UI and evidence loop

- Show the top actionable items with a short “why this may help” explanation, uncertainty metric before/after when computed, urgency basis, access/privacy caveats, and a link to the unresolved certificate or rival.
- Let the user verify/edit a source, deadline, and contact details; keep edits in an append-only reviewer-action log.
- Generate a plain-text/printable preservation-request draft with only user-confirmed details. Require an explicit user action to copy/download it; record that action without claiming it was sent.
- On new evidence intake, hash and preserve the original first, re-run only dependent analysis, invalidate stale outputs, and show before/after changes to the relevant certificates/rivals. Do not silently claim the added item resolved the question.

#### Acceptance checks

Use held-out staged scenarios with an independently declared informative missing observation. The top-ranked suggestion must target the relevant observation, and adding it must reduce the predeclared uncertainty/ambiguity metric by the preregistered amount. Include a negative case where every candidate has unknown availability/deadline; no camera owner or countdown may be invented. Verify every draft is unsent until a user action and every added artifact triggers proper hash/lineage and stale-run handling.

### Phase 5C — Prevention Atlas (opt-in, private by default)

#### Eligibility, privacy, and aggregation

Atlas inclusion is a separate, revocable, explicit consent from case participation and from media processing. Default is excluded. Store consent actor/time/scope/version and a revocation path. Exclude direct identifiers, original media, faces, plates, transcripts, exact incident dates, and free-text narratives from aggregate views. The Atlas stores only the minimal derived fields needed for the approved analysis: coarse location/junction cell, time bucket, road-user/trajectory/conflict descriptors, provenance class, uncertainty, source-case linkage in a separately protected access-controlled table, and duplicate-cluster key.

Require a configurable minimum cohort before showing a public or cross-organization aggregate; until a privacy review sets a justified threshold and re-identification tests, keep the Atlas internal to authorized case reviewers and use synthetic demo data. Apply spatial/time coarsening and query controls; prevent drill-down to individual cases for users without authorization. Do not claim anonymization solely because names were removed. Record each map query/export and include deletion/revocation propagation behavior. Revoked cases are excluded from future aggregations and rebuilds; previously exported aggregates are handled by documented retention policy.

Deduplicate repeat uploads or multiple camera clips from one event using a conservative event-cluster review flow. A candidate match is not an automatic merge. Count one incident once, preserve source case relationships, and require reviewer confirmation when matching is ambiguous.

#### Atlas product behavior

- Show junction-level aggregate patterns only when eligibility, consent, and cohort rules pass. Every marker reports sample count/coarsening, uncertainty, inclusion window, and whether it contains synthetic or observed cases.
- Separate measured/observed incidents from simulated intervention scenarios. Never plot a simulated scenario as a historical crash or near-miss.
- Allow a user to compare explicitly parameterized interventions over the included scenarios. Show per-scenario and aggregate changes, uncertainty/sensitivity, affected road-user groups, and conflicts/trade-offs. Label results as modeled hypotheses requiring transport/road-safety engineering review; do not output a construction recommendation or safety guarantee.
- No public link, bulk export, or external map tile/service may reveal precise incident locations without documented consent and privacy review.

#### Acceptance checks

Verify opt-in/opt-out behavior, revocation, access control, duplicate incident handling, cohort suppression, location/time coarsening, query logging, and no identifiers in aggregate payloads. Run a re-identification review on the selected synthetic/staged data and test that withheld cases cannot be singled out from map outputs. Intervention outputs must change when declared assumptions change and retain provenance; the interface must not imply causal or safety certainty.

### Phase 5D — PDF and JSON review export

#### Export contents and immutability

An export is a versioned snapshot tied to an exact case revision and must be reproducible from its manifest. Include:

- Case/export IDs, creation time, schema version, source acquisition notes, user-visible consent scope, and processing/reviewer event history.
- For each original media item: immutable storage reference or controlled inclusion decision, filename, byte length, MIME/codec metadata, SHA-256 at intake and re-verification at export, and integrity result. Never rewrite originals during export.
- Frame index and source citations as media ID plus frame index and presentation timestamp; every citation must resolve against the manifest.
- Clip synchronization method/offset/uncertainty; calibration anchors, coordinate system, scale, homography fit ID/error, and review status.
- Track source observations and corrections with provenance; model runs, exact input hashes, software/model versions, parameters, seeds, fit diagnostics, uncertainty contribution breakdowns, identifiability certificates, and stale/failure states.
- Claims, transcript provenance, verdict rules and citations; counterfactual interventions; rival-search bounds/objective/residuals; evidence-needs suggestions and human verification states; Atlas aggregation provenance only when consent and access policy allow it.
- Clear findings classes (`OBSERVED`, `MEASURED`, `ASSUMED`, `SIMULATED`, `UNKNOWN`), limitations, unvalidated interval coverage, missing evidence, and expert-review notes.
- Hashes for each export artifact and a manifest hash. JSON must be schema-validated, deterministic for the same snapshot, and contain no credentials, signed URLs, or unapproved personal data.

PDF is a readable human report with a concise executive summary, source inventory/integrity, timeline, annotated stills, calibration/track/dynamics tables, 2D and labelled 3D stills, claim ledger, uncertainty/identifiability, counterfactual/rival sections, evidence radar, limitations, and appendices for methods/provenance. Large originals are not embedded by default; offer an explicit encrypted/original-media package only if storage/consent policy permits. PDF statements must never exceed the status of their linked JSON evidence.

#### Export workflow and error behavior

Use a case-scoped export job with states `queued`, `running`, `complete`, `failed`, and `stale`. Before generation, snapshot the case revision and inputs; verify original hashes; exclude or visibly mark stale analyses; render from that snapshot; validate all references and JSON schema; hash final outputs; then persist an immutable export record. If any integrity check fails, block the export or clearly mark the affected original unavailable—never produce a clean-looking integrity assertion. Re-export after a case change creates a new version; it does not overwrite the prior package. Access/download is authenticated and audited.

### Phase 5E — fresh upload to export (G9) integration

The G9 scenario begins with an empty case and a never-before-processed staged clip. A tester follows the same UI path as a user: create case/consent → upload → wait for actual jobs → review/confirm track → calibrate or receive an explicit metric refusal → add a statement if in scope → view timeline and supported analyses → inspect 2D/3D → review evidence needs → create PDF/JSON export → verify source hash and frame links from the export.

The run must record screen/video evidence, timestamps, job IDs, exact commit/configuration, all manual interventions, failures/retries, export IDs and hashes, and final checklist. No database edits, mocked model responses presented as live, precomputed case outputs, hidden reviewer approvals, skipped job states, or cached results may stand in for steps. If a model is unavailable, exercise the declared fallback and label cached or synthetic material honestly. The fresh case must be independently inspectable from its exported manifest.

### API, persistence, and engineering sequence

Implement in this order to keep interfaces stable:

1. Define and version scene, evidence-need, consent/Atlas, reviewer-action, export-manifest, and job-state schemas. Add unit/serialization fixtures before wiring UI.
2. Add migrations and repository/service layer for immutable scene snapshots, rescue ranking snapshots, Atlas consent/aggregation metadata, export jobs/records, and their case/media/run foreign keys. Establish an explicit database migration baseline and stop using API startup `create_all()` for production schema changes.
3. Implement scene adapter and G7 numerical consistency checks; wire viewer and 2D fallback.
4. Implement deterministic radar scoring and human verification/status transitions; add staged acceptance fixtures.
5. Implement opt-in Atlas privacy/query/aggregation gates and synthetic-data demo; keep external/public Atlas disabled pending review.
6. Implement export snapshot builder, PDF renderer, JSON validator, hash verification, authenticated download, and audit events.
7. Run G7 unit/integration/browser checks, then G9 from a clean database/object store and fresh staged upload. Record scorecards and limitations.

Candidate endpoint contracts (final paths may follow existing API conventions):

```text
GET  /cases/{case}/media/{media}/scene3d              -> versioned scene payload
GET  /cases/{case}/evidence-needs                      -> ranked needs + status
POST /cases/{case}/evidence-needs/{need}/verification -> user-confirmed source/deadline
POST /cases/{case}/evidence-needs/{need}/draft         -> unsent request draft
GET  /atlas                                            -> authorized/cohort-qualified aggregates
POST /cases/{case}/atlas-consent                       -> explicit opt-in/out
POST /cases/{case}/exports                             -> immutable export job
GET  /cases/{case}/exports/{export}                    -> status + hashes
GET  /cases/{case}/exports/{export}/files/{kind}       -> authenticated PDF/JSON download
```

All routes are case-scoped, authenticated, schema-validated, and auditable. Long PDF work runs in a worker; deterministic small payloads may be synchronous. Do not expose original files or private case records through Atlas endpoints.

### G7 and G9 acceptance gates

- **G7 — 3D consistency:** at least 100 predeclared samples spanning all supported track types, scene transforms, and boundary timestamps match the 2D engine positions within the tolerance fixed before evaluation. Report fixture count, sample count, units, max/RMS error, missing-data behavior, and software revisions. Verify source-frame links and that scene rendering/mesh choices cannot modify engine values.
- **G7 — truthful rendering:** every synthetic geometry/view, counterfactual, rival path, and generated scene image has a visible persistent illustrative label in live UI and exported stills; observed track points remain distinguished. Unknown calibration/camera pose does not create confident-looking geometry.
- **G9 — clean end-to-end:** at least one fresh staged upload from an empty case completes the documented user-visible path to a schema-valid PDF/JSON export without hidden intervention. All source hashes re-verify, all frame references resolve, stale/failed outputs are disclosed, and the full manual-action/job ledger is included. Repeat once with a deliberate recoverable job failure and once with a missing calibration to verify explicit fallback/refusal.
- **Privacy and safety gate:** no unauthorized Atlas record access; opt-out and revocation are honored; export and Atlas audit events are present; no unverified camera owner/deadline is invented; no automatic external request is sent; no 3D render is described as ground truth.

### Phase 5 definition of done

Phase 5 is complete only when G7 and G9 artifacts are committed in `evaluation/scorecards/`, the schema/migrations/API/UI/fallbacks are reviewable, PDF and JSON agree on provenance and limitations, privacy controls pass, the fresh-path demo is reproducible, and the feature branch is pushed. If a production-ready baseline migration or privacy review is still pending, label that deployment boundary clearly; do not call the corresponding capability production-ready.

## Definition of done

A feature is complete only when its UI, typed data contract, provenance, failure behavior, measurement, and one meaningful acceptance case are present. A mock response, fixture replay, or prerecorded video may support development, but must never be presented as a fresh live model result.

## Suggested repository shape

```text
apps/web/                 Case UI, timeline, 3D viewer, exports
services/api/             Authenticated API and job orchestration
services/worker/          Media processing and model adapters
engine/geometry/          Camera and ground-plane calculations
engine/dynamics/          Motion fit, uncertainty, interventions
engine/evidence/          Claims, identifiability, rivals, rescue
contracts/                Schemas, units, provenance types
fixtures/                 Synthetic and staged consented examples
evaluation/               Ground truth, runners, scorecard
reports/                  Generated demo outputs (no secrets)
docs/                     These documents
```

## Repository structure (implementation blueprint)

Use one monorepo. Keep evidence and numerical logic in Python, the interface in TypeScript, and the shared API contract explicit. The tree below is the intended starting structure; add a directory only when its owner and contract are clear.

```text
blackbox/
├── README.md                         # setup, quick demo, limitations
├── LICENSE
├── .env.example                      # names only; never secrets
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml                # web, API, worker, Redis, Postgres, object store
├── Makefile                          # setup, test, lint, demo, export commands
├── pyproject.toml                    # Python dependencies and tool config
├── uv.lock                           # pinned Python dependencies
├── package.json                      # JS workspace scripts
├── pnpm-lock.yaml                    # pinned JS dependencies
├── apps/
│   └── web/                          # Next.js + TypeScript
│       ├── app/                       # routes: cases, review, atlas
│       ├── components/
│       │   ├── intake/                # upload, consent, source inventory
│       │   ├── player/                # synchronized source videos, frame seeking
│       │   ├── timeline/              # event and acoustic timeline
│       │   ├── claims/                # transcript, claim ledger, evidence jumps
│       │   ├── calibration/           # anchors, quality and uncertainty
│       │   ├── simulation/            # slider and sensitivity plots
│       │   ├── scene3d/               # R3F scene; display only
│       │   ├── evidence-rescue/        # missing-evidence ranking and drafts
│       │   └── atlas/                 # consented aggregated cases
│       ├── lib/                       # typed API client, units, time conversion
│       ├── state/                     # synchronized time and selection state
│       ├── public/                    # UI assets; no real case footage
│       └── tests/                     # component and browser-flow tests
├── services/
│   ├── api/                           # FastAPI
│   │   ├── main.py
│   │   ├── routes/                    # cases, media, jobs, claims, models, exports
│   │   ├── auth/                      # access checks and scoped media links
│   │   ├── db/                        # tables, migrations, repositories
│   │   ├── schemas/                   # Pydantic request/response types
│   │   └── tests/
│   └── worker/                        # Celery pipeline
│       ├── jobs/                      # one retryable stage per task
│       ├── media/                     # FFmpeg/PyAV probing and frame index
│       ├── meta/                      # SAM, Voice, Spark adapters
│       ├── exports/                   # report and manifest generation
│       └── tests/
├── engine/                            # pure, versioned numerical/evidence core
│   ├── geometry/                      # camera models, homography, scale
│   ├── tracking/                      # track cleanup and ground-contact points
│   ├── synchronization/               # audio/visual clip offset estimates
│   ├── dynamics/                      # forward model, fitting, posterior samples
│   ├── counterfactual/                # interventions and sensitivity
│   ├── evidence/                      # deterministic claim tests and citations
│   ├── identifiability/               # answerability certificates
│   ├── rival/                         # bounded alternate-hypothesis search
│   ├── rescue/                        # missing-evidence value and urgency
│   └── tests/
├── contracts/
│   ├── openapi.yaml                    # generated/reviewed HTTP contract
│   ├── schemas/                       # versioned JSON Schemas
│   ├── examples/                      # valid and invalid payloads
│   └── units.md                        # SI units and timestamp semantics
├── infra/
│   ├── docker/                         # service Dockerfiles
│   ├── migrations/                     # database migrations
│   └── deploy/                         # environment-specific deployment config
├── evaluation/
│   ├── ground_truth/                   # independent labels and measurement notes
│   ├── synthetic/                      # scene generators and seeds
│   ├── runners/                        # repeatable metrics and ablations
│   ├── scorecards/                     # dated results, including failures
│   └── tests/
├── fixtures/
│   ├── synthetic/                      # reproducible synthetic case inputs
│   └── staged/                         # consented demo inputs + consent metadata
├── scripts/                             # setup, smoke, integrity, demo commands
├── docs/                                # product/engineering docs in this folder
└── .github/
    ├── workflows/                       # lint, typecheck, tests, build
    ├── pull_request_template.md         # evidence and test checklist
    └── CODEOWNERS                        # optional, if a team uses it
```

**Keep out of Git:** `.env`, keys, real victim footage, raw case uploads, generated reports with personal data, local databases, model caches containing private media, and large temporary renders. Put only staged/consented or synthetic fixtures in `fixtures/`, with licensing/consent notes. Do not use Git LFS as a substitute for consent or access control.

### Ownership boundaries

- `engine/` must be importable without FastAPI, Celery, Meta credentials, or browser code. Numerical tests run offline.
- `services/worker/meta/` translates Meta responses into versioned contracts; it never writes physical verdicts.
- `apps/web/components/scene3d/` reads engine output via the API and does not recompute physics.
- `contracts/` is the shared source for units, provenance classes, and API shape; schema changes require compatibility review.
- `evaluation/` is separate from demo fixtures. Held-out cases remain held out during tuning.
- Original media lives in object storage, never under `apps/web/public/` or in a Git commit.

## Mandatory Git branch and push workflow

**Every project change must be made on a non-`main` branch, committed, and pushed to that branch. Do not commit or push directly to `main`.** This applies to code, docs, fixtures, configuration, and evaluation results. A change is not considered handed off until its branch is pushed to the configured remote and its branch name is recorded in the work log or pull request.

Use a short descriptive branch name, for example `feature/media-intake`, `feature/claim-checker`, `fix/frame-timestamps`, or `docs/repo-structure`. Before starting, create or switch to the branch and confirm the current branch. After the change, run relevant checks, inspect the diff for secrets and private footage, commit the work, and push the branch. Open a pull request for review before merging. Keep `main` protected where the Git host supports it.

```bash
git switch -c feature/media-intake
# make the change and run the relevant checks
git status --short
git diff --check
git add <specific-files>
git commit -m "Build source-preserving media intake"
git push -u origin feature/media-intake
```

If the remote is unavailable, retain the commit locally on the non-`main` branch and mark the push as pending. **Do not report it as pushed.** Resolve the remote/authentication issue and push the branch before calling the change delivered. Avoid `git add .` for cases that may contain sensitive media or keys; stage explicit files.

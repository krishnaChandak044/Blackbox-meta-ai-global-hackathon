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
12. Run held-out, controlled-real, safety, privacy, and end-to-end evaluations; ship report and demo.

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

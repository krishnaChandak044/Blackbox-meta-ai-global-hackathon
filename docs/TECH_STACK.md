# Blackbox — chosen technology stack

**Decision date:** 31 October 2026. Pin exact dependency versions in lockfiles when implementation starts; this document chooses components and boundaries, not untested version numbers.

## Stack at a glance

| Layer | Choice | Why |
| --- | --- | --- |
| Web app | Next.js + React + TypeScript | Case workflow, server-side routes, typed UI |
| Styling | Tailwind CSS + accessible headless components | Fast, consistent interface; keyboard and screen-reader support |
| 3D | Three.js + React Three Fiber | Orbitable evidence-linked scene driven by numerical trajectories |
| 2D timeline/plots | SVG/Canvas + lightweight plotting library | Frame-accurate tracks, uncertainty regions, sensitivity charts |
| Backend API | Python + FastAPI + Pydantic | Typed contracts close to CV and physics code |
| Media processing | FFmpeg/ffprobe + PyAV | Probe, decode, index presentation timestamps, create derived previews |
| CV/geometry | Meta SAM 3.1 API + OpenCV + NumPy | Tracking masks, camera calibration, homography, geometry |
| Language | Muse Voice Transcribe + Muse Spark | Timestamped speech and structured atomic claims; never numerical authority |
| Physics/inference | NumPy + SciPy; PyMC for posterior fitting and predictive checks | Deterministic forward engine and explicit uncertainty |
| Jobs | Celery + Redis | Durable asynchronous media/model/numerical jobs with retries |
| Database | PostgreSQL | Cases, manifests, corrections, jobs, findings, audit records |
| Object storage | S3-compatible store; local filesystem for development | Separate original and derived bytes, scoped access |
| Export | HTML + PDF renderer + JSON manifest | Human-readable and machine-readable case package |
| Testing | pytest; Playwright; type checks | Numerical, pipeline, and browser workflow validation |
| Local deployment | Docker Compose | Repeatable web, API, worker, Redis, Postgres, object-store setup |

## Frontend

Use Next.js with TypeScript and React. The case workspace has synchronized video panes, a timeline, frame annotation tools, a 2D map, claim ledger, assumption inspector, and 3D viewer. Keep 3D rendering in a client-only component. The 3D renderer receives `TrajectorySample[]`, `CameraPose[]`, and `UncertaintyRegion[]` from the API; it never computes verdicts. Use Three.js through React Three Fiber. Store UI state such as selected time and active claim in a single typed client store to keep the videos, plots, and 3D view synchronized.

Render masks and annotations as overlays over the actual video; use the exact frame presentation timestamp from the backend. A browser video player's apparent current time can drift from a discrete frame index, so the UI must show the resolved source frame reference for any cited finding. Provide keyboard controls and an always-visible `observed / estimated / simulated` legend.

## Backend and computation

FastAPI owns authenticated case APIs and job submission. Pydantic models mirror the data contracts in `DATA_CONTRACTS.md`. Heavy work runs in Celery workers, not HTTP request handlers; FastAPI itself recommends a larger task system for heavy background computation. [FastAPI background-task guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/), [Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html).

FFmpeg/ffprobe records codec, duration, audio, and timing metadata and generates playback copies. PyAV reads exact frame presentation timestamps and frame data for analysis; its documented `pts × time_base` semantics support variable-frame-rate material. [PyAV time documentation](https://pyav.org/docs/stable/api/time.html). Store original bytes before any transcode and hash all outputs.

OpenCV handles lens correction, homography, feature correspondences, and geometry checks. NumPy/SciPy implement the versioned forward dynamics model, fitting, numerical optimization, and bounded rival search. PyMC is for Bayesian parameter sampling and posterior predictive checks where a full posterior is needed; do not make the live slider wait for MCMC. Precompute posterior samples, then run the slider's interventions against those samples using the fast deterministic engine. [PyMC posterior predictive API](https://www.pymc.io/projects/docs/en/stable/api/generated/pymc.sample_posterior_predictive.html).

## Meta model integration

Use a server-side Meta Model API adapter with request/response logging that excludes secrets and private media contents from ordinary logs. SAM 3.1 supplies video masks and object tracks; parse stable object IDs and frame markers, then validate against the frame index. Muse Voice Transcribe supplies timestamped speech turns; it does not currently promise word-level timestamps. Muse Spark extracts atomic claims into a strict schema and explains typed findings. Prefer a dedicated speech endpoint for statements rather than relying on Spark's audio understanding, whose documentation notes limitations for Spark 1.3. [Meta Model API overview](https://dev.meta.ai/docs/overview), [Meta video/audio guidance](https://dev.meta.ai/docs/video-understanding), [SAM parser guidance](https://dev.meta.ai/docs/sam/client-libraries).

SAM 3D Objects is an optional asset-generation worker. The core 3D replay uses generic parametric meshes, so it remains functional without SAM 3D. Generated meshes are illustrative and do not alter object positions, collision geometry, or claim verdicts. Verify licensing and runtime separately.

## Storage and provenance

PostgreSQL stores structured case data and append-only reviewer actions. S3-compatible object storage holds original and derived media in separate prefixes/buckets. Hash original bytes on intake and on export. Each derived artifact records parent hashes, processor version, parameters, and output hash. Use scoped signed URLs for media access and short expirations. Do not put raw video or model keys in the database or frontend bundle.

For local work, a filesystem-backed object adapter is acceptable if it preserves the same manifest contract. In production, choose a managed S3-compatible service; keep the storage interface portable. Redis is a queue/broker, not the source of truth for case records.

## Service boundaries

```text
Browser (Next.js, video, charts, R3F)
    -> FastAPI (auth, cases, contracts, review, signed media URLs)
    -> PostgreSQL (metadata, findings, audit)
    -> object storage (originals and derivatives)
    -> Celery/Redis workers
         -> FFmpeg/PyAV media extraction
         -> Meta SAM / Voice / Spark adapters
         -> OpenCV geometry
         -> NumPy/SciPy/PyMC physics and inference
         -> export generation
```

## Repository layout

```text
apps/web/              Next.js app, synchronized viewer, R3F scene
services/api/          FastAPI routes, auth, Pydantic schemas
services/worker/       Celery jobs, Meta adapters, media processing
engine/geometry/       Camera calibration, homography, uncertainty
engine/dynamics/       Forward model, inference, interventions
engine/evidence/       Event rules, claim checks, answerability, rivals
contracts/             JSON Schema/OpenAPI, units, provenance statuses
fixtures/              Licensed/staged and synthetic test cases
evaluation/            Ground truth, metrics, scorecard runners
docs/                  Product and engineering documents
```

## Deployment choice

Develop with Docker Compose so the same services run on every machine. Host the web app and API where long-running workers and private object storage are supported. Avoid a pure serverless setup for video decoding, model streaming, or posterior sampling. Use one environment for the demo and test the fresh-upload path there. Add observability for job stage, error class, duration, model usage, and input/output manifest hashes, without logging sensitive footage or transcripts.

## Two choices to avoid

1. **A single giant Next.js server route for everything:** video and sampling jobs need retryable workers and durable state.
2. **A language model as the physics or legal engine:** all numerical results and claim tests must be reproducible from typed observations and explicit rules.

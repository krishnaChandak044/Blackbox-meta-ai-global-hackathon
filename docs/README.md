# Blackbox documentation

Start with [PRD.md](PRD.md). The product turns road-incident video and spoken accounts into a preserved, source-linked timeline, conditional simulations, and an illustrative 3D replay.

## Document map

| File | Purpose |
| --- | --- |
| `PRD.md` | Product scope, user flows, requirements, differentiation, acceptance criteria |
| `ARCHITECTURE.md` | Services, pipelines, model boundaries, reproducibility |
| `TECH_STACK.md` | Chosen languages, libraries, infrastructure, and service boundaries |
| `DATA_CONTRACTS.md` | Core entities, provenance, units, statuses, API contracts |
| `EVALUATION.md` | Datasets, ground truth, metrics, gates, release scorecard |
| `DEMO_AND_SUBMISSION.md` | Live demo, recording plan, judge-facing claims, submission checklist |
| `BUILD_PLAN.md` | Dependency order, workstreams, integration gates, definition of done |
| `SAFETY_PRIVACY.md` | Evidence handling, consent, retention, misuse and review boundaries |
| `COMPETITIVE_POSITION.md` | Existing tools, defensible differentiation, claims to avoid |
| `OPEN_DECISIONS.md` | Decisions that require a product owner or evidence from implementation |
| `FUTURE_FEATURES.md` | Prioritized feature candidates, research gates, and claims to avoid |

## Rules for every implementation decision

1. Preserve original media unchanged and link every derived artifact to it.
2. Separate observed, measured, assumed, simulated, and unknown facts in data and UI.
3. Statements are checked against a video-only reconstruction; they never train the result that checks them.
4. A generated 3D viewpoint is illustrative, never source footage.
5. A numerical result is complete only with units, assumptions, uncertainty, and a reproducible method.
6. When the evidence is insufficient, the product returns `undeterminable` or `not_identifiable`.
7. Make every project change on a non-`main` Git branch, commit it, and push that branch; see `BUILD_PLAN.md`.

The docs describe the intended product, not completed functionality. Update the scorecard in `EVALUATION.md` with actual results before submission.

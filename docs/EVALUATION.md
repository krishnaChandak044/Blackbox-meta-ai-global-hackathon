# Evaluation and release scorecard

This file is a plan until real results are recorded. Never copy target values into a results column as if measured.

## Evaluation sets

1. **Synthetic dynamics:** generated scenes with known speed, braking onset, deceleration, friction range, camera angle, timing offset, and controlled noise. Keep a held-out configuration set.
2. **Controlled real video:** staged, safe low-speed passes with fixed cameras, measured road distances, and independent timing/speed reference. Include oblique views, occlusion, compression, and poor light if safely practical.
3. **Statement benchmark:** independently authored supported, contradicted, and unobservable claims in at least two languages; include negation, vague time, and transcription errors.
4. **Evidence rescue benchmark:** remove one informative observation from a multi-view staged case, rank missing items, then add it and measure actual uncertainty reduction.
5. **Rival benchmark:** construct ambiguous single-view cases where two parameter sets fit, plus a second view that disambiguates them.
6. **3D consistency set:** sample timestamps and compare 3D object locations to the exact 2D engine output.

## Metrics

| Metric | Definition | Target to set before test | Actual |
| --- | --- | --- | --- |
| Tracking error | Pixel and ground-plane position error vs annotated truth | TBD | Not measured |
| Identity switches | Incorrect track ID changes per clip | TBD | Not measured |
| Sync error | Absolute clip offset error and interval coverage | TBD | Not measured |
| Calibration error | Reprojection and scale error on held-out anchors | TBD | Not measured |
| Speed error | Absolute and relative error where scale is valid | TBD | Not measured |
| Interval coverage | Fraction of truths inside nominal 90% interval | Near 90%, with sample count | Not measured |
| Claim precision | Correct supported/contradicted outcomes vs reviewers | TBD | Not measured |
| False contradiction rate | Wrongly contradicted claims / all truly non-contradicted claims | Minimize and report | Not measured |
| Abstention quality | Insufficient-evidence cases correctly withheld | TBD | Not measured |
| Counterfactual calibration | Known simulated intervention outcomes vs engine | TBD | Not measured |
| Rescue value | Uncertainty reduction after top suggested evidence | Positive vs baseline | Not measured |
| Rival recovery | Known alternate scenario found and later rejected | TBD | Not measured |
| 3D alignment | Difference between 3D object position and engine state | Numerical tolerance TBD | Not measured |
| End-to-end latency | Upload to review-ready result by clip length | TBD | Not measured |

## Required gates

- Original hash remains unchanged; every derived file has lineage.
- No metric speed when scale or calibration fails.
- No driver reaction-time inference without independent evidence.
- No statement used to fit the reconstruction that checks it.
- No unsupported frame citation.
- No unlabeled synthetic camera view.
- No counterfactual percentage without conditioning assumptions.
- A fresh real clip completes the demo path without hidden manual data changes.

## Evaluation protocol

Freeze test cases before tuning. Keep a separate development set. For each run, record code revision, model version, API mode, input hashes, seed, reviewer corrections, failures, exclusions, and runtime. Report sample size and confidence intervals. Show at least one failure example and one successful abstention. An in-sample or synthetic result must be labelled as such.

## Release evidence

Before submission, replace `Not measured` with measured values and links to reproducible run manifests. Write a one-page `RESULTS.md` with what worked, what failed, and what remains unvalidated. Do not call the product forensic-grade without qualified independent validation.

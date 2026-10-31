# Blackbox — Product Requirements Document

**Version:** 1.1
**Date:** 31 October 2026
**Target:** Meta Global AI Developer Hackathon 2026
**Product category:** Video-based road-incident investigation and prevention
**Working tagline:** *From scattered clips to a reviewable incident, and from an incident to a testable prevention hypothesis.*

## 1. Executive decision

Build Blackbox as an **evidence-first crash investigation workspace**. It accepts one to three original video clips and multilingual spoken or written accounts, preserves the media, creates a frame-cited event timeline, estimates trajectories when geometry permits, compares checkable statements against the observations, and runs explicit counterfactual scenarios. A synchronized 3D view makes the measured and simulated paths understandable. The product never equates a plausible rendering with proof.

The hackathon submission must show the complete chain on a real, staged, fixed-camera incident: **raw media → integrity record → synchronized tracks → calibrated 2D scene → independently checked statement → uncertainty-aware counterfactual → evidence-linked 3D replay → exportable review package**. Additional clips, languages, camera types, and incident classes expand coverage; they do not alter this core contract.

**Competitive thesis:** FrontierSight AI already demonstrates video-to-physics, trajectory views, and counterfactual braking. Blackbox wins its own category by making an investigation accessible and auditable: source-preserving intake, multi-source reconciliation, statement-to-frame verification, missing-evidence guidance, explicit abstention, and a prevention-oriented report. The 3D scene is a compelling interface, but the underlying evidence system is the differentiator.

**Honest promise:** Blackbox prepares and tests an investigation hypothesis. It does not authenticate a video merely because it has a hash, determine legal fault, recover an unseen driver reaction time, or establish that one hypothetical action would certainly have prevented a crash.

## 2. Problem and opportunity

Road incidents generate fragmented evidence: phone video, shop CCTV, dashcams, recordings of accounts, and often inconsistent clocks. A non-expert usually lacks a practical way to preserve originals, align the clips, locate the decisive moments, separate observations from assumptions, or make a concise package an expert can review. A polished AI summary can make this worse by silently filling gaps.

The initial beneficiary is a person affected by an incident who has video but cannot immediately access a reconstruction expert. Secondary users are legal aid teams, insurers, journalists investigating road design, road-safety nonprofits, and professional investigators who want a triaged case. Blackbox should reduce the time to produce a reviewable package and help identify what additional evidence is worth obtaining before it disappears.

The public-health framing is substantial: WHO reports **1.19 million road-traffic deaths per year** globally, and India's Ministry of Road Transport and Highways reports **172,890 fatalities in 2023**. These figures establish the scale of harm; they do not establish the addressable market or prove that every incident has usable footage. The pitch should not state that aviation became safe *solely* because of investigations. ICAO describes accident investigation as a mechanism for prevention and safety recommendations, without assigning blame. Blackbox borrows that prevention principle for roads.

## 3. Product positioning

### 3.1 One-line description

Blackbox turns video and testimony into a source-linked road-incident timeline, then tests specific prevention scenarios across the range of conditions the evidence permits.

### 3.2 What the user receives

1. An immutable original-media inventory with hashes and metadata.
2. A synchronized timeline of directly observed events with frame-level citations.
3. A top-down trajectory reconstruction with visible calibration assumptions and uncertainty.
4. A claim ledger: supported, contradicted, or undeterminable, with reasons and source frames.
5. An interactive what-if workbench that changes one explicit parameter at a time and reports conditional outcomes.
6. An orbitable 3D explanatory replay, linked to the clips and visibly distinguished from measured evidence.
7. A review package containing media inventory, methods, assumptions, findings, limitations, and a machine-readable trace.

### 3.3 Product boundaries

The system must not issue a legal-fault verdict, identify a person from a face, assert intent, infer impairment, or present a generated camera angle as historical footage. It may flag observable rule-relevant facts such as a visible stop-line crossing, but jurisdiction-specific right-of-way conclusions require a reviewed rule set, complete scene evidence, and a human review marker.

## 4. Users and jobs

| User | Job to be done | Successful outcome |
| --- | --- | --- |
| Person affected by a crash | Preserve and organize media before it is lost | A shareable package whose key claims open the source frames |
| Legal aid or advocate | Understand what is supported and what remains contested | Rapid triage, clear uncertainty, no invented conclusions |
| Collision expert | Inspect how measurements and assumptions led to a hypothesis | Editable calibration, reproducible computation, exportable tracks |
| Road-safety group | Learn whether a junction design contributed | Aggregated, privacy-protected prevention hypotheses |
| Insurer or claims reviewer | Review factual sequence efficiently | Original media, event table, citations, processing log |

## 5. Scenarios

### 5.1 Primary demonstration case

A fixed camera records a staged, harmless near-miss at a marked junction. A second phone clip records the same event from another viewpoint. One participant says in Hindi, “I had already stopped before the line.” The system preserves both videos, aligns them, tracks the vehicle and the line, and shows the relevant frames. If the vehicle crosses the line while still moving, it marks the precise claim **contradicted**; if the line is hidden, it marks it **undeterminable**. The reviewer moves a braking-onset slider, sees an outcome range in 2D and 3D, and opens the assumptions behind that range.

### 5.2 Other supported cases

- A pedestrian crossing incident with one fixed camera and a partially occluded path.
- A two-vehicle junction collision with two cameras and a visible traffic light.
- A dashcam-only case where the system can extract a timeline but refuses unsupported absolute speed claims.
- A clip with missing or unreliable audio; synchronization proceeds by visual landmarks or manual alignment.
- A case with inconsistent testimony; the system compares each discrete observable claim, without branding a person as dishonest.

### 5.3 Deliberate abstention case

A low-resolution night clip shows only a brief blur before impact. Blackbox preserves and timestamps it, identifies visible objects if possible, and states which questions cannot be answered. This is a required demonstration of reliability, not a failure to hide.

## 6. End-to-end workflow

### 6.1 Intake and preservation

The user creates a case, uploads one to three clips, and optionally records statements. The app stores the **original bytes unchanged**, computes SHA-256, captures filename, size, codec, frame rate, variable-frame-rate status, audio streams, timestamps and time-zone information where available, and records the upload time. Derived files are separate, with their own hashes and a parent-link to the original. Every transformation enters a processing log: tool version, parameters, operator or model, input hashes, output hashes, and UTC time.

The interface must explain that a hash documents file integrity *from intake forward*; it does **not** prove that the source was authentic before upload. The user can download the original at any time. Temporary previews are access controlled and can be deleted without deleting the preservation record until the user requests case deletion.

### 6.2 Scene and camera setup

The user identifies the incident area and confirms any known real-world measurement: surveyed line distance, visible road marking, curb length measured on site, or a documented object dimension. The interface distinguishes measured anchors from default assumptions. Lens distortion, camera movement, zoom, frame timing, and perspective are estimated or flagged. If metric scale is absent, the system uses relative motion and refuses absolute speed or stopping-distance conclusions.

### 6.3 Perception

SAM 3.1 segments and tracks vehicles, pedestrians, bicycles, road boundaries, stop lines, and visible signals using short concept or object prompts. A separate classifier or model can propose concepts, but tracking output is converted into typed observations and reviewed for identity switches, occlusion, and bad masks. Users can correct a track; the correction is logged and the original model result remains inspectable.

### 6.4 Synchronization

The system estimates clip offsets from shared audio transients, visual events, and metadata. Each method produces a confidence or uncertainty interval. The reviewer can align clips manually using two matching events. Blackbox must not assume the sound of impact exists in every clip, nor that device timestamps are accurate. Event-time intervals propagate into downstream estimates.

### 6.5 Geometric reconstruction

For fixed cameras, a ground-plane homography converts tracked ground-contact points into scene coordinates. The calibration module reports reprojection error, anchor quality, lens and perspective caveats, and a distribution over plausible transforms. Moving cameras require a separate motion-estimation workflow and may be restricted to relative kinematics when scale cannot be established. Every point retains the source clip, frame, mask, contact-point choice, and uncertainty.

### 6.6 Dynamics inference

A deterministic dynamics engine models position, velocity, heading, braking onset, deceleration and collision/near-miss geometry. Bayesian or likelihood-based inference samples parameters that reproduce observed tracks **under stated priors**. It must expose parameter correlations and non-identifiability. Driver reaction time is not a default inferred quantity: a camera may show brake onset, but the driver's perception time is usually unobserved. Friction is an assumption or a measured input unless evidence constrains it. The output includes posterior predictive fit to the visible tracks, not just parameter estimates.

### 6.7 Statement analysis

Muse Voice Transcribe converts speech to text with speaker and language metadata where available. Muse Spark extracts **atomic, checkable claims** into a schema: subject, action, spatial or temporal relation, qualifiers, original-language span, translated paraphrase, and ambiguity flags. Each claim is checked **against video-derived observations independently of the statement**. Testimony can be displayed alongside the reconstruction, but it cannot be used to fit the same trajectory that later “verifies” it. The checker returns supported, contradicted, or undeterminable, plus the decisive frames, uncertainty and reasoning steps. A person can edit the transcript or claim interpretation; edits are versioned.

### 6.8 Counterfactual workbench

The reviewer selects an intervention: earlier braking, different approach speed, altered visibility, changed signal timing, or road-design change. The simulator runs the intervention over the parameter distributions compatible with the observed event. The UI reports outcomes as **conditional model results**: “Under these calibration and braking assumptions, 82 of 100 sampled scenarios avoid contact.” It shows sensitivity to assumptions, including best- and worst-supported cases. It must never label the sampled proportion as the probability that the historical crash would have been avoided.

### 6.9 3D explanation

The 3D viewer uses the same timestamped trajectories and uncertainty envelope as the 2D engine. Orbit, scrub, pause, inspect an object, switch camera vantage, and compare observed versus counterfactual paths. An evidence mode overlays source-camera frustums and marks regions or time spans unseen by any camera. SAM 3D Objects may generate an **illustrative** vehicle mesh from a masked image; fallback parametric meshes must always work. The UI labels meshes, unseen surfaces, inferred poses, and synthetic views. A click on any event jumps to the original source frame and the corresponding calculation. No evidence is derived from the appearance of the generated mesh.

### 6.10 Review and export

The user reviews each finding, accepts or disputes track corrections, and exports a PDF/HTML report plus a JSON evidence manifest. The export clearly separates: **observed**, **measured/estimated**, **assumed**, **simulated**, and **unknown**. It includes original hashes, processing history, clip synchronization, calibration, model versions, frame citations, parameter intervals, sensitivity analysis, reviewer actions, and limitations. Shareable media can blur faces and plates; originals remain separately available to the case owner.

## 7. Functional requirements

IDs define the minimum contract and make scope auditable.

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| IN-01 | Upload 1–3 MP4/MOV clips and at least one audio or text statement | End-to-end case from supported files |
| IN-02 | Preserve originals, compute SHA-256, log all derived artifacts | Hashes match on re-download; manifest lists lineage |
| IN-03 | Detect variable frame rate and use presentation timestamps | Known irregular-timestamp fixture stays correctly ordered |
| SY-01 | Align two clips by shared event or manual anchors | Offset and uncertainty shown; reviewer can adjust |
| CV-01 | Track at least two moving actors across a clear fixed-camera scene | Track error measured against annotated frames |
| CV-02 | Record occlusion and identity uncertainty | No fabricated uninterrupted path through a long occlusion |
| GE-01 | Calibrate fixed-camera ground plane from reviewed anchors | Reprojection residual and scale uncertainty shown |
| GE-02 | Refuse metric speed when scale is missing or calibration fails | Explicit no-speed result on an uncalibrated clip |
| PH-01 | Fit a 2D motion model to measured tracks | Observed versus predicted path plotted; residuals available |
| PH-02 | Sample plausible parameters and preserve correlations | Interval and pairwise dependency view available |
| PH-03 | Flag parameters that are weakly identifiable | Reaction-time and friction claims withheld when unsupported |
| CL-01 | Transcribe at least two supported languages | Original transcript and translation linked to audio spans |
| CL-02 | Extract atomic claims and check them independently | Each finding has source frames or an insufficiency reason |
| CL-03 | Allow human correction with audit trail | Before/after claim versions retained |
| CF-01 | Change braking onset and approach speed independently | Reproducible simulation outputs for same inputs and seed |
| CF-02 | Show sensitivity, not a single outcome percentage | Outcome changes as uncertainty assumptions change |
| V3-01 | Orbit and scrub a 3D scene synchronized to 2D and video | Event positions match 2D engine at tested timestamps |
| V3-02 | Distinguish observed, inferred, and hypothetical geometry | Legend and per-object provenance visible throughout replay |
| V3-03 | Link each event to the original frame | One click opens the exact clip and timestamp |
| EX-01 | Export a readable and machine-readable review package | Independent reviewer can reproduce headline numbers |
| PR-01 | Generate a blurred share copy without changing originals | Hash of original unchanged; blur verified on sampled frames |
| ER-01 | Rank missing evidence by expected uncertainty reduction and urgency | Top recommendation improves a predeclared metric in held-out staged cases |
| ER-02 | Draft, but never send, a precise preservation request | Draft names source, location, time window, and why it matters |
| ID-01 | Produce an answerability certificate for each numerical claim | Certificate lists data, assumptions, ambiguity, and status |
| RH-01 | Search bounded rival scenarios that fit the same observations | Known alternative found in an ambiguous test and rejected by added evidence |
| PA-01 | Aggregate consented, deduplicated cases at one junction | No personal identifiers in the aggregate; source types labelled |

## 8. Scientific and technical design

### 8.1 Data model

Core entities: `Case`, `SourceMedia`, `DerivedArtifact`, `Camera`, `CalibrationAnchor`, `TrackObservation`, `Track`, `TimeAlignment`, `Event`, `Statement`, `AtomicClaim`, `Finding`, `ModelRun`, `ParameterSample`, `Intervention`, `CounterfactualResult`, `ReviewerAction`, and `ExportManifest`. Every derived finding carries a lineage path to source media and frame/time ranges. No model-produced prose is accepted as a numerical source of truth.

### 8.2 Typed tool boundary

Muse Spark may call read-only tools such as `get_track_window`, `get_event_frame`, `get_calibration`, `compare_claim_to_event`, and `run_counterfactual`. Tool responses are structured, versioned, and include units. The language model may translate and explain; it may not modify numerical verdicts returned by the deterministic engine. A schema validator rejects missing units, impossible timestamps, and source references that do not exist.

### 8.3 Uncertainty propagation

Represent at least five uncertainty sources: tracking location, camera calibration, timing offset, model parameters, and missing/occluded observations. Propagate them into trajectories and counterfactual results by sampling, with a fixed random seed recorded in the manifest. Display data-supported intervals separately from scenario ranges driven mainly by priors. If uncertainty is so broad that an intervention cannot be ranked reliably, the UI says so.

### 8.4 3D architecture

Use a right-handed world coordinate system with the ground plane at `z=0`; define units and origin in the manifest. The 3D scene renders objects from typed trajectories; it does not infer motion from meshes. A generic vehicle proxy is the baseline; SAM 3D-generated assets are optional replacements with source-image attribution and an “illustrative geometry” label. Camera frustums, occlusion volumes, uncertainty tubes, and counterfactual ghost paths can be toggled. The final render must remain usable if SAM 3D is unavailable.

### 8.5 Prevention layer

The prevention view groups counterfactuals by intervention type: behavior, signal timing, visibility, and physical road layout. It is a hypothesis generator for road-safety review, not an automated engineering recommendation. A junction-level pattern requires multiple independently documented incidents or near misses; one case cannot establish a systemic design defect.

## 9. Evaluation plan

**Synthetic ground truth:** generate scenes with known speed, braking onset, deceleration, camera intrinsics, perspective, and timing offsets. Render videos with controlled noise, compression, occlusion, dropped frames, and clock drift. Measure tracking error, calibration error, trajectory error, event-time error, parameter recovery, and whether nominal 90% intervals cover ground truth at approximately the advertised rate across many trials.

**Real controlled footage:** record staged, low-speed passes in a safe area with a stationary camera, measured distances, and independent speed/time reference. Include daylight, oblique perspective, occlusion, and at least one poor-quality case. Report failures and exclusions. Do not stage a real collision or near-collision involving people.

**Statement set:** create statements with known supported, contradicted, and unobservable claims. Include multilingual recordings, negation, vague timing, and conflicting accounts. Score claim extraction separately from claim verification. Report false contradiction rate as a primary safety metric.

**Counterfactual checks:** test conservation of units, monotonic expectations under bounded conditions, integration stability, collision geometry, and sensitivity to friction and timing. Compare a known simulated intervention with the engine output. Ensure the UI never reports a precise avoided percentage when the posterior is dominated by assumptions.

**3D checks:** verify coordinate alignment against the 2D engine at sampled timestamps; confirm that source-frame links work; verify all synthetic views retain a visible label; verify that changing mesh shape alone cannot change the physical outcome.

**Human review:** ask at least one independent reviewer to inspect exported reports without guidance. Measure whether they can identify what was observed, what was assumed, and what would require an expert. Record confusion as a product defect.

The public scorecard must list dataset size, scene types, camera types, metric definitions, in-sample versus held-out results, and known failure cases. A single clean demo clip is not validation of general accuracy.

## 10. Go/no-go quality gates

1. **Integrity gate:** originals remain byte-identical; all transformations are logged.
2. **Grounding gate:** every supported or contradicted claim opens a valid source frame and an explicit test rule.
3. **Calibration gate:** metric speed is withheld if scale or fit quality is inadequate.
4. **Independence gate:** statements do not influence the video-only reconstruction used to check them.
5. **Uncertainty gate:** the counterfactual report states its conditioning assumptions and broadens when the input quality worsens.
6. **Visualization gate:** all 3D camera angles outside source footage are labelled synthetic or illustrative.
7. **Reproducibility gate:** the same manifest, model versions, and seed regenerate the same numerical result.
8. **Demo gate:** a fresh supported upload completes without manual database edits or hidden prerecorded output.

If a gate fails, disable that claim in the product and report the limitation. Feature count does not compensate for a false evidence claim.

## 11. Non-functional requirements

**Privacy:** case access is private by default; sharing requires an explicit action; originals and derived share copies are separate; deletion and retention behavior are stated in the UI. Avoid sending real victim media to third-party model services without informed permission. For demo, use staged or licensed footage.
**Security:** server-side API keys, encrypted transport, scoped file URLs, upload limits, content-type inspection, and audit logs.
**Performance:** previews should appear while analysis runs; long jobs expose progress and resume safely. Aim for a complete short-clip demo in minutes, measured on the actual deployment.
**Accessibility:** captions, keyboard controls, color-independent confidence markings, readable uncertainty summaries, and language-preserving transcripts.
**Reliability:** failed model calls do not corrupt the case; each stage can retry from preserved inputs.
**Portability:** export does not require the hosted service to understand the evidence manifest.

## 12. Model and tool roles

| Component | Role | Failure boundary |
| --- | --- | --- |
| SAM 3.1 | Segment and track road users and scene features | Masks and identities require checks; no physics verdict |
| Muse Voice Transcribe | Convert speech into timestamped text | Transcript is editable and not treated as fact |
| Muse Spark | Extract atomic claims, propose scene queries, explain typed outputs | Cannot invent frame references or override engine results |
| SAM 3D Objects | Generate illustrative object geometry from a mask/image if practical | Mesh is never evidence of unseen shape or path |
| Deterministic geometry/physics engine | Calibration, kinematics, simulation, uncertainty propagation | Abstains when inputs are insufficient |
| Human reviewer | Correct observations, approve reports, identify missing evidence | Actions and revisions are logged |

Meta's hackathon page explicitly highlights Muse Spark, Muse Image, SAM 3.1, open weights, and Muse Code. SAM 3D Objects exists as a separate Meta research offering; verify its license, environment requirements, and acceptance in the specific contest before treating it as a scored integration. The product's 3D view must not depend on it.

## 13. Competitive map and differentiation

| Existing work | What it already provides | Blackbox's required distinction |
| --- | --- | --- |
| FrontierSight AI | Video-to-physical-state analysis, uncertainty, trajectory and braking what-ifs | Incident-specific intake, source preservation, multilingual testimony, independently checked claims, evidence-linked export |
| Amped FIVE / PC-Crash / Virtual CRASH | Professional video analysis and collision reconstruction | Accessible guided workflow for a non-expert, with expert-readable provenance rather than a hidden verdict |
| RoadSentinel | Dashcam capture and reporting for individuals | Cross-clip reconstruction, frame-cited claim checking, conditional simulation |
| Daari Sentinel | Incident detection and driver warning | Post-incident review and prevention hypothesis testing |

Do not claim that nobody has built crash reconstruction, that every tool targets fleets, or that a 3D slider is novel by itself. The defensible novelty is the **integrated, evidence-first workflow for a person with limited resources**, if the implementation and evaluation prove it.

## 13A. Distinguishing capabilities to pursue

These four additions address gaps in the investigation workflow. They are **proposed differentiators, not a claim that no other product has them**. They count only when they work end to end and their limitations are visible.

### A. Evidence Rescue Radar — find the missing evidence before it disappears

Blackbox should infer what would most reduce uncertainty in the current case and turn it into a concrete collection plan. If a vehicle disappears behind a bus just before the conflict point, the app identifies the missing time window, estimates which nearby camera viewpoints *could* see it from a user-supplied map or street photo, and drafts a preservation request that names the place, date, and exact time range. It can also ask for a scene measurement, original camera export, signal log, or vehicle event data when those would matter more than another video. This is a **recommendation for a human to act on**; the app must never claim a camera exists or send a request automatically.

The ranking algorithm should estimate expected reduction in uncertainty for each obtainable item, alongside urgency, access difficulty, and privacy cost. A map may use public points of interest, but nearby businesses are possible contacts, not verified CCTV owners. A user can mark evidence as requested, received, unavailable, or refused, with timestamps and provenance.

**Demo:** Remove the second camera from a staged case. Radar identifies the specific blind interval and shows that obtaining the second clip or one measured road distance would collapse different uncertainty bands. Add the clip and show the change quantitatively.

**Acceptance:** For a held-out staged scenario, the top suggestion must identify a genuinely informative missing observation; adding it must reduce a predeclared uncertainty metric. False claims about camera existence are zero. A preservation draft is never sent without the user's explicit action.

### B. Identifiability Map — show which questions the footage can answer

For every requested conclusion, Blackbox should generate a machine-readable **answerability certificate**: the observation needed, the available source, the calibration dependency, uncertainty contributors, and whether different parameter combinations explain the same footage. The UI shows a compact map of how each claim depends on evidence. For example, brake onset may be weakly estimable from a visible velocity change, whereas driver reaction time remains unobservable without knowing when the hazard was perceived.

This goes beyond a generic confidence score. Use profile-likelihood or posterior-dependency checks, sensitivity analysis, and synthetic perturbations to test whether an estimate is constrained by data or merely by the prior. The result can be `measurable`, `conditional`, or `not identifiable`. The reviewer can select a missing measurement and preview how it might change answerability.

**Demo:** The system refuses to answer “How fast was the car?” without a scale anchor, then accepts a measured line-to-line distance and produces a speed interval with a recorded calibration error. It continues to refuse “When did the driver notice the pedestrian?”

**Acceptance:** In synthetic scenes constructed with parameter ambiguity, Blackbox must flag non-identifiability rather than return narrow intervals. With a valid new anchor, it must narrow the interval at a measured rate without losing held-out coverage.

### C. Rival-hypothesis workbench — search for a plausible alternative explanation

The original proposal's two debating agents are replaced by a stronger mechanism: a **bounded rival-hypothesis search**. For a contested claim, the engine seeks a materially different scenario that still fits the source observations within error: alternate clip offset, ground-plane calibration, occluded path, braking onset, or object identity. If it finds one, the report shows both hypotheses and the evidence that would distinguish them. If it does not, it reports the search space and limits—not “proof that no alternative exists.” Muse Spark can explain the comparison in plain language, but the search and fit tests are deterministic.

This is valuable because an impressive reconstruction can be wrong while still looking smooth. The rival-hypothesis view forces Blackbox to show whether a claimed conclusion survives plausible alternative assumptions.

**Demo:** Show two different reconstructions that both fit a single camera. Add a second camera; one becomes inconsistent with observed frames. The change is visible in the 2D and 3D views.

**Acceptance:** The system recovers a known alternative in a synthetic ambiguous case and rejects it when disambiguating evidence is supplied. It logs the parameter bounds and search method, and never states that a bounded search exhausted all possible realities.

### D. Prevention Atlas — turn isolated incidents into local design hypotheses

With consent, Blackbox can convert multiple cases at the **same junction** into a privacy-protected conflict map: trajectories, conflict points, visibility gaps, and near-miss patterns. Analysts can test a proposed intervention such as moving a stop line, changing a signal phase, or removing a visual obstruction across the collected scenarios. The output ranks proposals by modeled conflict reduction, uncertainty, and likely trade-offs. It does not claim a design is safe or recommend construction without engineering review.

The atlas must require minimum case counts and strip personal identifiers before aggregation. A single crash may generate a hypothesis but cannot establish a junction-level pattern. The simulator must distinguish recorded incidents from synthetic what-if cases and avoid counting multiple uploads of the same event as independent evidence.

**Demo:** Load several staged or licensed near-miss scenarios at one synthetic junction. Show a repeated conflict location, test two interventions, and reveal that one helps one road user while worsening another—then show the sensitivity to traffic assumptions.

**Acceptance:** Duplicate uploads are deduplicated; every aggregate point links to a consented case or labelled simulation; withheld cases cannot be reverse-identified from a public map; and the intervention ranking changes appropriately when scenario assumptions change.

### Priority and why these matter

1. **Evidence Rescue Radar** is the strongest product differentiator: it acts while missing footage or measurements might still be obtained. Official video-acquisition guidance stresses timely, integrity-preserving retrieval; the radar turns that principle into a user workflow. [UK Home Office guidance](https://assets.publishing.service.gov.uk/media/62a9f18fd3bf7f036bb12944/Recovery_and_Acquisition_of_Video_Evidence_v3-0.pdf).
2. **Identifiability Map** is the strongest scientific differentiator: it demonstrates when the system *cannot* know something, then shows what specific new measurement would change that.
3. **Rival-hypothesis workbench** is the strongest live-demo twist: judges watch a plausible 3D story get challenged by evidence rather than merely narrated by agents.
4. **Prevention Atlas** creates the long-term network effect and turns case review into a public-safety use case. Existing traffic-conflict tools show this analysis is meaningful, so Blackbox should claim an accessible evidence-to-intervention workflow rather than novelty of conflict metrics. [FHWA Surrogate Safety Assessment Model](https://highways.dot.gov/turner-fairbank-highway-research-center/software/ssam).

Avoid adding a binary “deepfake authentic/not authentic” badge. Video authentication is a specialized, uncertain task, and current camera-fingerprint methods have notable limits on compressed or stabilized footage. Blackbox may flag metadata inconsistencies and document source history, but it should refer suspicious media to an expert rather than certify authenticity. [INTERPOL review](https://pmc.ncbi.nlm.nih.gov/articles/PMC13285715/).

## 14. Demonstration script

**0–20 seconds:** A person describes a disputed junction incident. Show two untouched uploaded clips and their hashes.
**20–50 seconds:** Blackbox aligns the views, overlays tracks, and shows the decisive timeline event with source-frame jumps.
**50–75 seconds:** Play a Hindi statement. Show transcription, the atomic claim, and the exact frames that contradict it. Open an ambiguous second claim and show “cannot determine.”
**75–105 seconds:** Switch to the top-down and orbitable 3D scene. Toggle source-camera visibility and uncertainty bands; make the synthetic-view label obvious.
**105–135 seconds:** Move the braking-onset slider. Show the distribution of outcomes and sensitivity to friction and timing assumptions.
**135–155 seconds:** Open the rival-hypothesis view and show how the second clip rules out one plausible explanation. Show the answerability map and a specific missing measurement that would reduce uncertainty.
**155–175 seconds:** Show Evidence Rescue Radar's preservation draft, then export the review package and trace a claim back to original bytes and calculations.
**Optional extended demo:** In Prevention Atlas, compare two junction interventions across consented or synthetic scenarios, with a visible trade-off.

The demo should use a fresh, safe, staged clip processed by the actual pipeline. A cached case may be shown for speed, but the live processing path must be available and honestly identified.

## 15. Build order without removing features

The full product scope is retained. Sequence the implementation so every layer consumes verified outputs from the previous one:

1. Case schema, original-media storage, hashes, and lineage.
2. Fixed-camera tracking, timestamp handling, and a source-frame viewer.
3. Calibration and 2D trajectory engine with refusal rules.
4. Voice transcription and independent atomic-claim checking.
5. Dynamics inference and uncertainty propagation.
6. Counterfactual simulator and sensitivity view.
7. Synchronized 3D viewer with generic meshes, then SAM 3D assets.
8. Multi-camera alignment, expert corrections, export, and privacy copies.
9. Evidence Rescue Radar, answerability certificates, bounded rival-hypothesis search, and the consented Prevention Atlas, each with its own measured acceptance case.
10. Held-out evaluation, honest scorecard, live demo rehearsal, and packaging.

This is a dependency order, not a reduced feature list. A feature is complete only when its acceptance evidence is present.

## 16. Success metrics

**Hackathon:** end-to-end live case; valid frame citations for every claim; one correctly supported, one correctly contradicted, and one correctly undeterminable statement; measured calibration and tracking error; a counterfactual result with assumptions and sensitivity; a 3D replay whose events link to original frames; a useful missing-evidence recommendation; one correctly identified non-identifiable parameter; a rival scenario resolved by added evidence; and a reproducible exported report.

**Product pilot:** median time from upload to review-ready package; reviewer time saved; proportion of claims judged correctly versus expert annotation; false contradiction rate; rate of justified abstention; percentage of reports with complete source lineage; and whether users understand the distinction between evidence and simulation.

**Longer-term impact:** whether evidence is preserved sooner, whether experts can triage more cases, and whether aggregated, privacy-protected findings lead to concrete road-safety changes. Do not infer lives saved from a prototype.

## 17. Open decisions

1. Indie or startup track, and the exact accepted rules and disclosure requirements.
2. First target geography and languages; India is a strong starting context but needs local user validation.
3. Whether SAM 3D Objects can run reliably in the available deployment environment.
4. Which source footage can be used publicly with consent and a clear license.
5. How an independent expert will review the report format and physics assumptions.
6. Whether the first pilot is direct-to-person, legal aid, or expert-assist. The hackathon demo should not pretend this has been validated.

## 18. References and verification notes

- [WHO, Global status report on road safety 2023](https://www.who.int/teams/social-determinants-of-health/safety-and-mobility/global-status-report-on-road-safety-2023): 1.19 million annual deaths estimate.
- [India Ministry of Road Transport and Highways, Road Accidents in India 2023](https://morth.gov.in/sites/default/files/Road-Accident-in-India-2023-Publications.pdf): 172,890 reported fatalities.
- [ICAO, Annex 13 background](https://www.icao.int/sites/default/files/postalhistory/annex_13_aircraft_accident_and_incident_investigation.htm): investigation aims at prevention and does not apportion blame.
- [SWGDE, Best Practices for Digital Forensic Video Analysis](https://www.swgde.org/documents/published-complete-listing/18-v-001-best-practices-for-digital-forensic-video-analysis/): source preservation, processing documentation, and integrity checks.
- [ForeSpeed research dataset](https://arxiv.org/abs/2512.19364): real-world CCTV speed estimation is sensitive to camera conditions and perspective.
- [Meta Global AI Developer Hackathon](https://dev.meta.ai/events/global-hackathon): tracks, themes, featured tools, and public schedule.
- [Meta SAM 3.1 documentation](https://dev.meta.ai/docs/sam/segmenting): video segmentation and tracking interface and limits.
- [Meta SAM 3D](https://ai.meta.com/sam3d): single-image object reconstruction; separately verify deployment terms.
- [UK Home Office, Recovery and Acquisition of Video Evidence](https://assets.publishing.service.gov.uk/media/62a9f18fd3bf7f036bb12944/Recovery_and_Acquisition_of_Video_Evidence_v3-0.pdf): video collection and preservation guidance.
- [FHWA Surrogate Safety Assessment Model](https://highways.dot.gov/turner-fairbank-highway-research-center/software/ssam): established conflict-analysis framework for traffic trajectories.
- [INTERPOL review of forensic image and video analysis, 2022–2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC13285715/): limitations of source-camera fingerprinting and authentication.
- [FrontierSight AI](https://github.com/tamzid2001/frontiersight-ai), [Daari Sentinel](https://github.com/ChaitanyaReddy01/daari-sentinel), [RoadSentinel](https://roadsentinel.ai/en), [Amped FIVE](https://ampedsoftware.com/five), [PC-Crash](https://pc-crash.com/), [Virtual CRASH](https://www.vcrashusa.com/forensics): competitive context.

# Blackbox — Feature candidates and research roadmap

**Updated:** 31 October 2026
**Status:** Proposed features and experiments, not completed capabilities or a prediction of hackathon placement.

Blackbox's central promise is a preserved, source-linked account of what video shows, what remains unknown, and what conditional simulations suggest. A feature belongs in the product only if it strengthens that promise. See `PRD.md` for current requirements; this file records additional ideas and how they should be treated.

## Priority summary

| Priority | Feature | Why it matters | Status relative to PRD |
| --- | --- | --- | --- |
| 1 | Synchronized multi-camera source player | Lets reviewers inspect the same moment from each original view | Promote to core UI requirement |
| 2 | Acoustic and visual event cross-check | Adds an independent timing signal for horns, impact-like sounds, and braking noises | Add to evaluation and timeline |
| 3 | Evidence-need and answerability view | Shows what cannot be answered and which obtainable item would help | Already covered by Evidence Rescue Radar and Identifiability Map; strengthen UI |
| 4 | Versioned frame annotation studio | Allows a reviewer to correct ground-contact points, road lines, and event labels with an audit trail | Extend track-correction workflow |
| 5 | Uncertainty and visibility overlay | Makes weakly observed trajectories and blind spots obvious in 2D and 3D | Strengthen existing 3D/2D requirements |

These are the best *product* additions. They do not guarantee a top-one-percent result. The demo must still prove that the system works on fresh footage and reports measured errors.

## A. Build into the core experience

### A1. Synchronized multi-camera source player

Play up to three source clips on one timeline using explicit clip-offset estimates and uncertainty. Scrubbing one view seeks the others to the same estimated world time. Show an offset range when synchronization is ambiguous. A reviewer can set two matching anchors and version the correction. Never label views “perfectly aligned” without validation.

**Acceptance:** On a staged two-camera event with an independent timing reference, report synchronization error; clicking an event in any view opens corresponding frames in the others or indicates that the event is outside their coverage.

### A2. Acoustic and visual event cross-check

Detect candidate horns, impact-like transients, and tire-squeal-like sounds. Treat them as **candidate acoustic events**, because audio alone may not identify the source. Align them with visual events and show agreement or disagreement. Use the sounds to propose clip offsets, not as unquestioned anchors.

**Acceptance:** On labelled recordings, report precision, recall, and timestamp error for each supported sound class. A missing or noisy audio track must not prevent visual-only analysis.

### A3. Versioned frame annotation studio

Permit a reviewer to mark stop lines, signal state, vehicle ground-contact points, occlusion boundaries, and calibration anchors directly on a source frame. Preserve the original frame and every prior annotation version. Record who changed what, when, why, and which downstream calculations were recomputed.

**Acceptance:** A correction produces a new version and a visible diff; the exported report identifies findings changed by the correction. Annotation history and hashes document processing but do not, by themselves, establish legal admissibility.

### A4. Uncertainty and visibility overlay

Display confidence as intervals, paths, or regions with text labels, not only red/green colors. Mark where no camera observed the road user and distinguish interpolated motion from observed points. The overlay must share coordinates with the 2D engine and 3D replay.

**Acceptance:** A staged occlusion increases the visible uncertainty region; adding a second useful view shrinks it. A user can inspect the exact source frames and assumptions behind the change.

### A5. Road-condition observations

Flag visible wet pavement, potholes, faded markings, obstructed signs, and similar conditions as **observations or review prompts**. Do not automatically call them causal contributors. Link each flag to source frames, confidence, and human review. Only a separately specified, evaluated model may estimate effects on braking or visibility.

**Acceptance:** The system distinguishes “wet-looking surface visible” from “road friction measured” and from “caused this incident.”

## B. Context integrations: useful, but never automatic verdicts

### B1. Historical weather context

Fetch source-attributed historical weather for the approximate place and time. Show dataset name, spatial resolution, temporal resolution, and distance from the incident. Use it to suggest a hypothesis, not to assert exact junction visibility, road wetness, or wind at the collision point. Open-Meteo historical reanalysis can be around 9 km resolution for recent data, so localized conditions may differ. [Open-Meteo historical API](https://open-meteo.com/en/docs/historical-weather-api).

**Acceptance:** The UI says “regional historical estimate” and does not overwrite contrary source footage or on-scene measurements.

### B2. Jurisdiction-specific traffic-rule references

Support one reviewed jurisdiction at a time, with rule text, source, version/effective date, and applicability conditions. Mark directly visible facts (for example, a line crossing) separately from the legal interpretation. A person reviews any rule-relevant finding. “India, UK, US, EU” is not one unified rules database; local and temporal differences matter.

**Acceptance:** Every displayed rule cites its official source and applicable date; unsupported jurisdictions return no rule verdict.

### B3. Speed-limit lookup

Use map data only to suggest a possible limit. Confirm against visible signage, authoritative records, and the incident date before comparing it with estimated speed. If the map tag is missing, variable, or stale, show “limit unverified.” OpenStreetMap documents speed-limit tags and variable limits, but coverage and correctness are not guaranteed. [OSM speed limits](https://wiki.openstreetmap.org/wiki/Speed_limits).

**Acceptance:** No “X% above limit” finding is issued from an unverified map value or an uncalibrated speed estimate.

### B4. Preservation urgency

The Evidence Rescue Radar may list nearby *possible* camera sources and draft precise requests. It must not claim a camera exists, knows the owner, or overwrites in 24/48/72 hours without confirmation. Use “retention unknown” by default. A user can record a verified deadline and receive a countdown based on that source.

**Acceptance:** No fabricated camera or retention claim appears in the case report; preservation messages are drafts until a user sends them.

## C. Scientific experiments with explicit validation gates

### C1. Video anomaly triage

Check metadata inconsistencies, frame timing discontinuities, codec changes, and selected visual artifacts. Report **which tests were run and what anomalies they found**. Do not emit a general “authentic” or “no tampering” badge. An anomaly may have benign causes; absence of a detected anomaly does not prove authenticity. A qualified examiner handles consequential authentication questions. [SWGDE video-authentication guidance](https://www.swgde.org/documents/published-complete-listing/23-v-001-best-practices-for-digital-video-authentication/).

**Gate:** Evaluate on camera originals, benignly edited videos, and known manipulations; report false-positive and false-negative rates per test.

### C2. Road-friction estimation

Treat friction as an uncertain model parameter, not a directly visible fact. Deceleration depends on brake application, vehicle condition, grade, load, and road surface. A video track alone may not identify friction separately from these variables. Use independent measurements or explicit priors when available.

**Gate:** Demonstrate identifiability on controlled footage with ground truth and report parameter correlation and interval coverage; otherwise retain friction as an assumption.

### C3. Monocular depth

Use monocular depth to improve scene layout or object placement, but do not accept its scale as a measurement without calibration. Single-view depth has an inherent scale ambiguity, even when models predict plausible metric depth from learned priors. [Scale-ambiguity research](https://arxiv.org/abs/2410.02924).

**Gate:** Compare against measured scene distances and camera viewpoints; reject depth-driven speed or collision findings when error is too high.

### C4. Driver-state inference

Do not infer distraction, impairment, panic, or gaze from road-facing footage. An inward-facing camera, visible face, consent, validated model, and a distinct review process would be required even to explore some attention-related observations. The product must not make character or intent judgments from motion patterns.

**Gate:** No driver-state output in the hackathon product. Revisit only with a separate scientific and privacy review.

## D. Visualization and scale candidates

### D1. Guided replay

A concise, source-linked walkthrough may pause at decisive frames, highlight measured tracks, and open the corresponding 3D illustration. It must preserve original playback speed and provide a visible distinction between original video and generated rendering. Avoid a “cinematic” social-media framing for real victims or court use.

### D2. VR / spatial mode

WebXR can be an optional viewer for the same typed 3D scene. It does not add evidentiary certainty. Build only when the ordinary orbitable viewer is correct and accessible.

### D3. Prevention Atlas and cross-case patterns

The PRD already covers consented, deduplicated incident aggregation and tested junction interventions. Add public heatmaps only after re-identification risk, minimum group size, and location sensitivity are reviewed. A modelled “40% conflict reduction” must specify dataset, intervention, assumptions, uncertainty, and whether it was validated on held-out observations. A single case cannot establish a junction-level design flaw.

### D4. Expert review network

A future pathway to a qualified collision engineer, legal-aid organization, or insurer could make the case package useful after the hackathon. Verify credentials, scope of service, fees, jurisdiction, and conflicts of interest before calling it a marketplace. Do not claim experts provide a “final verdict” automatically.

## Removed as headline features

- **Two agents debating prosecution versus defense:** the PRD's bounded rival-hypothesis search produces a more testable challenge to the reconstruction. Language models may explain hypotheses, but rhetorical debate is not evidence.
- **Behavior prediction, impairment, and gaze from road-facing video:** unsupported or easily misinterpreted.
- **Automatic legal-grade weather/speed findings:** the external data and geometry may not support those conclusions.
- **Social-media-ready crash film:** inappropriate as the primary product outcome; use a sober review walkthrough.

## Competitive proof to show judges

1. Two original clips play in sync, with measured offset error.
2. A spoken claim resolves to exact source frames; another correctly abstains.
3. The answerability map shows one question that cannot be inferred and the measurement that would help.
4. A rival reconstruction fits one camera but fails when the second view is added.
5. The what-if slider changes a conditional scenario distribution, with sensitivity visible.
6. The 3D replay is clearly labelled illustrative and links back to originals.
7. A fresh upload and export work end to end, with an honest scorecard.

That is a stronger demonstration of Blackbox than maximizing feature count or visual drama alone.

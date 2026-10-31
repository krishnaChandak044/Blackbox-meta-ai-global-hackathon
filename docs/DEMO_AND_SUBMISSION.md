# Demo and submission plan

## Single sentence for judges

“Blackbox preserves the original road-incident footage, shows exactly what each camera supports, checks spoken accounts against source frames, and tests prevention scenarios across explicit uncertainty.”

## Demo case

Use a staged, harmless fixed-camera junction near-miss and a second synchronized viewpoint. Obtain participant consent. Measure at least one real-world distance before filming and independently record the controlled movement timing. Keep the original files. Prepare one supported, one contradicted, and one undeterminable spoken claim.

## Live sequence (approximately three minutes)

1. **Problem:** show two clips and a disputed account; explain why a simple video summary is insufficient.
2. **Integrity:** display original hashes, clip metadata, and processing lineage.
3. **Timeline:** overlay tracks; click a detected crossing event to open the exact source frames in both clips.
4. **Statement:** play a short multilingual account; show atomic claim extraction and the three-way evidence result.
5. **Identifiability:** show a speed interval supported by a measured anchor and a question Blackbox refuses to answer.
6. **3D:** orbit the reconstructed scene; show the synthetic-view label, uncertainty envelope, camera frustums, and source-frame jump.
7. **What-if:** move the braking-onset slider; compare outcome samples and sensitivity to assumptions.
8. **Rival:** display a second plausible story that fits one view, then add the second clip and show why it no longer fits.
9. **Rescue:** remove the second clip or a measurement and show the ranked missing-evidence suggestion and preservation draft.
10. **Export:** open the report and trace one finding to the original clip and exact processing run.

The Prevention Atlas can appear as a short extended demo or a separate screen, using multiple consented or synthetic scenarios with clear labels.

## Claims to say

- “This event is visible in these frames.”
- “Under these calibration assumptions, the estimated speed range is ...”
- “The claim conflicts with an observed crossing event.”
- “In these simulated scenarios, earlier braking changes the outcome.”
- “This camera cannot tell us when the driver first saw the hazard.”

## Claims not to say

- “The generated 3D view is what actually happened.”
- “This proves fault, intent, or dishonesty.”
- “The original video is authentic because we hashed it after upload.”
- “The crash would certainly have been prevented.”
- “Nobody else has built video crash reconstruction.”

## Submission materials

- Public or review-accessible source repository with clear new-work history and setup instructions.
- Hosted demo or reproducible local launch path.
- Short video that follows the live sequence and shows actual pipeline output.
- Evaluation scorecard with measured results, exclusions, and failure cases.
- Original demo-media license/consent statement; no real victim footage.
- Architecture and model-use diagram.
- Privacy and limitation statement.
- One export package a judge can inspect without an account, using staged media only.
- Exact contest track, theme, rules, and current deadline verified in the accepted participant portal.

## Rehearsal gate

Run the demo from a clean case on the deployed environment. Test the upload, job progress, failure recovery, frame links, 3D alignment, voice path, export, and fallback when SAM 3D is unavailable. Time the live path. A cached example may shorten the presentation but must be labelled cached.

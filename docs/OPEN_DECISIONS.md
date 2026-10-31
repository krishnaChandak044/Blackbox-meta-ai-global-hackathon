# Open decisions

Record the owner, date, and evidence for each decision before release.

| Decision | Current default | Evidence needed |
| --- | --- | --- |
| Hackathon track and theme | Unselected | Accepted participant portal and official rules |
| First jurisdiction and languages | India; English and Hindi demo | User interviews and usable voice-model tests |
| Public demo footage | Staged, consented near-miss | Written consent, safe filming plan, measured scene |
| Primary camera support | Fixed camera first; dashcam conditional | Held-out calibration and tracking results |
| SAM 3D use | Optional illustrative mesh; generic fallback | License, compute, model access, reliability tests |
| Hosting and retention | Private-by-default case storage | Deployment design, privacy review, cost and deletion test |
| Minimum calibration quality | Block metric speed on failure | Held-out coverage and expert review |
| Counterfactual outcome language | Conditional scenario fraction | Comprehension test with independent reviewers |
| Export format | PDF/HTML + JSON + source manifest | Expert review of whether package is usable |
| First pilot buyer/user | Person plus legal aid reviewer | Interviews and willingness-to-use evidence |
| Prevention Atlas publication | Private analyst view first | Consent, aggregation privacy test, road-safety expert review |

## Next concrete actions

1. Verify contest rules, track, exact deadline, allowed third-party model use, and submission requirements.
2. Capture staged footage and ground-truth measurements with consent.
3. Run SAM 3.1 on the actual footage before designing the rest of the demo around its output.
4. Ask one qualified crash reconstruction or video-forensics practitioner to review the methods and report format.
5. Fill `EVALUATION.md` with measured results; document failures rather than editing the target after seeing them.

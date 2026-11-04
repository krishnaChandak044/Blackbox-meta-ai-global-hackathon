# Blackbox Prevention Atlas — Forensic Privacy Review & Posture

> **Version:** 1.0.0  
> **Status:** Passed Privacy Gates (Internal & Synthetic Staged Evaluation)  
> **Classification:** Internal Forensic Architecture & Data Governance  
> **Primary Module:** [`services/api/routes/atlas.py`](file:///Users/LENOVO/Desktop/Blackbox/services/api/routes/atlas.py)  
> **Test Suite:** [`evaluation/tests/test_atlas_privacy.py`](file:///Users/LENOVO/Desktop/Blackbox/evaluation/tests/test_atlas_privacy.py)

---

## 1. Executive Summary

The **Prevention Atlas** aggregates derived, post-investigation kinematic insights across multiple road incidents to reveal hazardous road designs, high-conflict junction patterns, and systemic near-miss corridors.

Because road incidents often involve sensitive visual media, individual victims, and potential legal disputes, the Atlas operates under a **Strict Zero-Reidentification Guarantee** and a **Private-by-Default** security posture. No incident can be aggregated without explicit, isolated user consent, and all aggregated outputs undergo irreversible spatial and temporal coarsening combined with $k$-anonymity cohort suppression.

---

## 2. Privacy Gates & Threshold Configuration

The Atlas enforces five layered mathematical and procedural privacy gates before any data is aggregated:

| Gate | Mechanism | Threshold / Setting | Security Objective |
|---|---|---|---|
| **Gate 1: Isolated Opt-In** | Explicit consent separation | `SCOPE_VERSION = "atlas-derived-coarse-v1"` | Prevents general case review consent from implicitly opting into public/cross-case analysis |
| **Gate 2: Spatial Coarsening** | Bounded Geohash truncation | Length 4 to 5 (`~4.9 km` to `~20 km` cells) | Eliminates exact GPS coordinates; prevents linking to private addresses or driveways |
| **Gate 3: Temporal Coarsening** | Calendar quarter bucketing | `YYYY-Q[1-4]` (e.g. `2026-Q4`) | Prevents cross-referencing against exact emergency call timestamps or weather logs |
| **Gate 4: Cohort Suppression** | Strict $k$-anonymity threshold | `MIN_COHORT = 5` distinct cases | Suppresses any junction, corridor, or cell with fewer than 5 independent incidents |
| **Gate 5: Human-in-the-Loop** | Reviewer sign-off | `reviewer_confirmed = True` | Blocks raw automated model outputs from polluting prevention insights |

### 2.1 Threshold Rationales

1. **Minimum Cohort Size ($k \ge 5$):**  
   In empirical privacy studies on spatial trajectories, a cohort size of $k \ge 5$ combined with coarse geographic resolution prevents linkage attacks even when adversaries possess auxiliary knowledge (such as knowing an acquaintance had a crash in a certain suburb during a given quarter).
2. **Geohash Length 4–5:**  
   - Length 4: $\approx 39.1 \times 19.5\text{ km}$ ($780\text{ km}^2$) — regional arterial level.
   - Length 5: $\approx 4.9 \times 4.9\text{ km}$ ($24\text{ km}^2$) — municipal district level.
   - Any geohash with length $> 5$ (which would resolve to block or intersection scale) is strictly rejected at the schema validator layer.
3. **Quarterly Bucketing:**  
   Incidents occurring within a 90-day window are mapped to identical temporal buckets. Exact seconds, hours, and calendar days are discarded.

---

## 3. Data Minimization & Aggregate Exclusion Matrix

The Prevention Atlas enforces strict data minimization. The table below specifies exactly what fields are admitted, derived, and strictly excluded from aggregate payloads:

| Category | Admitted / Stored in Private Contribution | Included in Aggregate Output | Strictly Excluded & Blocked |
|---|---|---|---|
| **Geographic** | Coarse Geohash (`u4pr`, `9q8yy`) | Coarse Geohash only | Exact GPS lat/long, street addresses, postcodes, camera mounting coordinates |
| **Temporal** | Calendar Quarter (`2026-Q4`) | Calendar Quarter only | Exact incident timestamp, time of day, day of week, video frame numbers |
| **Visual Media** | *None (zero media stored)* | *None* | Raw video clips, still frames, faces, vehicle bodies, surroundings |
| **Identifiable Assets** | *None* | *None* | License plates, vehicle registration, VINs, driver names, witness names, case IDs |
| **Conflict Semantics** | Whitelisted enum (`crossing`, `rear_end`, `turning`, `merge`, `other`) | Aggregated incident count | Free-text accident narratives, officer opinions, fault determinations |
| **Road Users** | Whitelisted counts (`pedestrian`, `cyclist`, `motor_vehicle`, `other`) | Summed cohort mix | Vehicle make/model/color, pedestrian demographics, clothing, age, gender |
| **Kinematic Metrics** | Whitelisted keys (`conflict_count`, `minimum_ttc_s`, `p95_speed_kmh`, `near_miss_count`) | Mean metric across cohort | Raw trajectory point clouds, raw speed traces, acceleration waveforms |

---

## 4. Consent Lifecycle & Instant Revocation

### 4.1 Separate Opt-In
General case creation consent permits processing only for private evidence review. A separate, explicit call to `POST /cases/{case_id}/consent` with `opted_in=True` is required before any contribution can be created. Attempting to add a contribution without this consent returns an immediate `409 Conflict`.

### 4.2 Instant Revocation Propagation
Consent can be revoked at any time by the case owner via `POST /cases/{case_id}/consent` with `opted_in=False`.

**Immediate Database Purge:**
```sql
DELETE FROM atlas_contributions WHERE case_id = :case_id;
```
1. All contribution records belonging to the case are immediately and permanently deleted from `atlas_contributions`.
2. The revocation is immediately recorded in the immutable audit log table `atlas_consent_events`.
3. If the deletion of this case causes the cell's distinct case count to drop below `MIN_COHORT = 5`, the entire cell is instantly suppressed from all future aggregate responses.

### 4.3 Immutable Audit Trail
Every consent event records:
- `id`: Unique UUID
- `case_id`: Associated case
- `opted_in`: Boolean status change
- `scope_version`: Active privacy policy scope (`atlas-derived-coarse-v1`)
- `actor`: Authenticated user ID
- `created_at`: UTC timestamp

---

## 5. Re-Identification Verification & Test Suite

The automated verification suite in [`evaluation/tests/test_atlas_privacy.py`](file:///Users/LENOVO/Desktop/Blackbox/evaluation/tests/test_atlas_privacy.py) executes continuous tests against these controls:

- `test_spatial_coarsening_rejects_exact_coordinates`: Proves GPS coordinates and high-precision geohashes raise schema validation errors.
- `test_time_bucketing_rejects_exact_timestamps`: Proves exact ISO timestamps and calendar dates are rejected.
- `test_unconfirmed_contributions_rejected`: Proves contributions without human reviewer verification are rejected with HTTP 422.
- `test_separate_consent_required_before_contribution`: Proves unconsented cases cannot contribute data.
- `test_cohort_suppression_below_threshold`: Proves small-N cells ($N < 5$) are withheld from aggregate outputs and only unlock when $N \ge 5$.
- `test_no_direct_identifiers_in_aggregate_payload`: Proves zero PII or direct identifiers leak into aggregate responses.
- `test_opt_out_and_revocation_purges_contributions`: Proves consent revocation immediately purges contributions and suppresses sub-threshold cohorts.
- `test_consent_audit_trail_recorded`: Proves immutable event logging for all consent modifications.

---

## 6. Public Release Prerequisites

The Prevention Atlas is currently authorized for **internal, authenticated, synthetic staged evaluation only**. Before enabling the Atlas for production deployments with real incident data or cross-organizational public dashboards, the following prerequisites must be met:

1. **Differential Privacy Budgeting:** Implement $(\epsilon, \delta)$-differential privacy noise addition (Laplace or Gaussian mechanism) on numeric aggregate metrics (`p95_speed_kmh`, `minimum_ttc_s`) to guarantee privacy against composition attacks.
2. **Third-Party Privacy & Security Penetration Audit:** Formal external review of the geohash coarsening and database deletion cascades.
3. **Data Protection Agreements (DPA):** Legal framework for municipal road authorities adhering to GDPR Article 9 and CCPA guidelines regarding derived road event insights.
4. **Automated Redaction Verification:** Automatic verification that any preview or thumbnail associated with contributing cases has passed automated face and license plate masking.

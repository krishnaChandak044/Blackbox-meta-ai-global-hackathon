<div align="center">

<img src="https://img.shields.io/badge/Meta%20AI%20Hackathon-2026-blue?style=for-the-badge&logo=meta" />
<img src="https://img.shields.io/badge/Status-In%20Development-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />

# 🖤 Blackbox

### *From scattered clips to a reviewable incident — and from an incident to a testable prevention hypothesis.*

**An AI-powered, evidence-first road crash investigation workspace.**  
Built for the **Meta Global AI Developer Hackathon 2026**.

</div>

---

## 🚨 The Problem

Every year, **1.19 million people die on roads globally** (WHO, 2023). In India alone, **172,890 fatalities** were recorded in 2023.

Most incidents generate fragmented evidence — phone videos, shop CCTV, dashcams, and inconsistent witness accounts. A non-expert has **no practical way** to:
- Preserve originals before they're deleted
- Align multiple camera angles
- Separate what was *observed* from what was *assumed*
- Build a package that an expert or lawyer can actually review

Polished AI summaries make this worse by silently filling gaps with invented conclusions.

**Blackbox fixes this.**

---

## 💡 What is Blackbox?

Blackbox turns **1–3 video clips + witness testimony** into a fully auditable investigation package — the way aviation uses black box recordings to prevent future crashes, applied to road incidents.

> Upload video → get a verified, source-linked, expert-readable investigation report.

---

## 🎯 What You Get

| Output | Description |
|--------|-------------|
| 📦 **Media Inventory** | SHA-256 hashed originals with full lineage tracking |
| ⏱️ **Event Timeline** | Frame-cited, synchronized sequence of events |
| 📐 **Trajectory Reconstruction** | 2D top-down vehicle paths with calibration uncertainty |
| ✅ **Claim Ledger** | Each witness statement marked: supported / contradicted / undeterminable |
| 🔀 **What-If Simulator** | "What if braking started 0.5s earlier?" with sensitivity analysis |
| 🌐 **3D Replay** | Orbitable, scrubable 3D scene — clearly labeled as illustrative |
| 📄 **Review Package** | Exportable PDF + JSON report with full source lineage |

---

## 🧠 Core AI Stack

| Component | Role |
|-----------|------|
| **SAM 3.1** | Segment and track vehicles, pedestrians, road markings |
| **Muse Voice Transcribe** | Convert multilingual speech to timestamped text |
| **Muse Spark** | Extract atomic claims, verify against video evidence |
| **SAM 3D Objects** | Generate illustrative vehicle geometry (optional) |
| **Physics Engine** | Deterministic kinematics, uncertainty propagation, counterfactuals |

---

## 🔑 Key Principles

1. **Preserve originals unchanged** — every derived artifact links back to source
2. **Separate facts from assumptions** — observed / measured / assumed / simulated / unknown
3. **Statements never influence the reconstruction that checks them**
4. **A generated 3D view is illustrative, never source footage**
5. **When evidence is insufficient → return `undeterminable`, not a guess**

---

## 🗺️ Feature Highlights

### 🔍 Evidence Rescue Radar
Identifies missing evidence *before it disappears* — estimates which nearby cameras could have captured the incident, drafts a preservation request, and shows countdown timers per source.

### 🗂️ Identifiability Map
For every question, generates an *answerability certificate*: what data is needed, what's available, what's unknowable. Shows the difference between "uncertain" and "unanswerable."

### ⚔️ Rival Hypothesis Workbench
Searches for alternative explanations that also fit the observed footage. Adds a second camera → one hypothesis becomes inconsistent. Live visual drama, rigorous science.

### 🛡️ Prevention Atlas
Aggregates consented, anonymized cases at the same junction to identify recurring conflict patterns and test infrastructure interventions — turning individual reviews into road-safety insights.

---

## 👥 Who Is It For?

| User | Use Case |
|------|----------|
| 🧑 Accident victim | Preserve and organize evidence immediately |
| ⚖️ Lawyer / Legal aid | Rapid triage — what's proven vs. disputed |
| 🏦 Insurance reviewer | Factual sequence with full source citations |
| 🔬 Collision expert | Editable calibration, reproducible computation |
| 📰 Journalist | Investigate road design failures with data |
| 🌍 Road safety NGO | Aggregated, privacy-protected junction analysis |

---

## 🏗️ Build Order

```
1. Case schema → media storage → hashes → lineage
2. Fixed-camera tracking → timestamp handling → source-frame viewer
3. Calibration → 2D trajectory engine → refusal rules
4. Voice transcription → atomic claim checking
5. Dynamics inference → uncertainty propagation
6. Counterfactual simulator → sensitivity view
7. Synchronized 3D viewer
8. Multi-camera alignment → export → privacy copies
9. Evidence Rescue Radar → Identifiability Map → Rival Hypothesis → Prevention Atlas
10. Evaluation → scorecard → live demo
```

---

## 🚀 Getting Started

> ⚠️ Project is currently in active development. Setup instructions will be added as the stack is finalized.

```bash
git clone https://github.com/krishnaChandak044/Blackbox-meta-ai-global-hackathon.git
cd Blackbox-meta-ai-global-hackathon
```

---

## 📊 Quality Gates

Before any feature is considered done, it must pass:

- ✅ **Integrity gate** — originals remain byte-identical
- ✅ **Grounding gate** — every claim cites a valid source frame
- ✅ **Calibration gate** — speed withheld if scale is unknown
- ✅ **Independence gate** — statements don't influence the reconstruction that checks them
- ✅ **Uncertainty gate** — counterfactuals state their assumptions
- ✅ **Visualization gate** — all synthetic 3D views are labeled
- ✅ **Reproducibility gate** — same manifest + seed = same result
- ✅ **Demo gate** — fresh upload works without hidden prerecorded output

---

## ⚠️ What Blackbox Does NOT Do

- ❌ Issue legal fault verdicts
- ❌ Authenticate a video as genuine (flags anomalies; refers to experts)
- ❌ Identify people from faces
- ❌ Assert driver intent or impairment
- ❌ Present generated camera angles as real footage
- ❌ Claim a counterfactual *would* have prevented a crash

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with ❤️ for safer roads · Meta Global AI Developer Hackathon 2026

</div>

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { phase4Api } from "@/lib/api";
import type { CounterfactualResponse, DynamicsRun } from "@/lib/api";

export default function SimulatePage({ params }: { params: { id: string; mediaId: string } }) {
  const { id: caseId, mediaId } = params;
  const [baseline, setBaseline] = useState<DynamicsRun | null>(null);
  const [shift, setShift] = useState(-0.4);
  const [speed, setSpeed] = useState("");
  const [decel, setDecel] = useState("");
  const [result, setResult] = useState<CounterfactualResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { phase4Api.getDynamics(caseId, mediaId).then(setBaseline).catch((e) => setError((e as Error).message)); }, [caseId, mediaId]);

  const run = async () => {
    if (!baseline || baseline.status !== "done") return;
    setBusy(true); setError(null);
    try {
      setResult(await phase4Api.simulate(caseId, mediaId, {
        baseline_run_id: baseline.run_id,
        braking_onset_shift_s: shift,
        entry_speed_override_kmh: speed.trim() ? Number(speed) : null,
        decel_override_ms2: decel.trim() ? Number(decel) : null,
      }));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const points = result?.simulated_points ?? [];
  const coords = points.map((p) => [Number(p.world_x_m), Number(p.world_y_m)] as const);
  const xs = coords.map(([x]) => x), ys = coords.map(([, y]) => y);
  const minX = Math.min(...xs, 0), maxX = Math.max(...xs, 1), minY = Math.min(...ys, 0), maxY = Math.max(...ys, 1);
  const polyline = coords.map(([x, y]) => `${30 + 540 * (x - minX) / Math.max(maxX - minX, 0.001)},${270 - 240 * (y - minY) / Math.max(maxY - minY, 0.001)}`).join(" ");

  return <main className="page-content fade-in" style={{ maxWidth: 1000, margin: "0 auto" }}>
    <div className="page-header"><p><Link href={`/cases/${caseId}/media/${mediaId}/dynamics`}>Dynamics report</Link> / Simulation</p><h1>Counterfactual simulator</h1><p>Change explicit model inputs and inspect the scenario path.</p></div>
    {error && <div className="alert alert-error">{error}</div>}
    <div className="alert" style={{ background: "var(--sand-light)", padding: 14, borderRadius: 10, marginBottom: 16 }}><strong>ILLUSTRATIVE — model scenario, not observed fact.</strong> The simulator assumes constant speed before onset, then constant deceleration along the initial heading. It does not model steering, friction, grade, or reaction time.</div>
    <section className="card card-body" style={{ marginBottom: 18 }}>
      {!baseline ? <p>Load or run a dynamics analysis first.</p> : <>
        <label className="form-label">Braking onset shift: {shift.toFixed(2)} s<input aria-label="Braking onset shift" type="range" min="-2" max="2" step="0.05" value={shift} onChange={(e) => setShift(Number(e.target.value))} /></label>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 12 }}>
          <label className="form-label">Scenario entry speed (optional, km/h)<input className="form-input" type="number" min="0" max="250" value={speed} onChange={(e) => setSpeed(e.target.value)} placeholder={baseline.entry_speed_kmh?.toFixed(1) ?? "Required if not identifiable"} /></label>
          <label className="form-label">Scenario deceleration (optional, m/s²)<input className="form-input" type="number" min="0.1" max="20" value={decel} onChange={(e) => setDecel(e.target.value)} placeholder={baseline.mean_decel_ms2?.toFixed(2) ?? "Required if not identifiable"} /></label>
          <button className="btn btn-primary" disabled={busy || baseline.status !== "done"} onClick={() => void run()}>{busy ? "Simulating…" : "Run scenario"}</button>
        </div>
        <p className="text-xs" style={{ marginTop: 12 }}>Baseline run {baseline.run_id.slice(0, 10)} · selected values are scenario inputs, not estimates of what happened.</p>
      </>}
    </section>
    {result && <section className="card card-body">
      <h2 className="heading-sm">{result.illustrative_label}</h2>
      {result.extrapolation_outside_support && <p className="alert alert-error">This scenario extends beyond the selected limits or observed time span. Interpret with extra caution.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, margin: "14px 0" }}>
        <Metric label="Scenario stopping distance" value={result.stopping_distance_m == null ? "Unavailable" : `${result.stopping_distance_m.toFixed(2)} m · illustrative point scenario`} />
        <Metric label="Scenario stopping time" value={result.stopping_time_s == null ? "Unavailable" : `${result.stopping_time_s.toFixed(2)} s after scenario start`} />
      </div>
      {points.length > 1 && <svg viewBox="0 0 600 300" role="img" aria-label="Illustrative counterfactual trajectory" style={{ width: "100%", background: "var(--bg-secondary)", borderRadius: 12 }}><text x="20" y="25" fontSize="13">ILLUSTRATIVE simulated path — not measured footage</text><polyline points={polyline} fill="none" stroke="var(--sky)" strokeWidth="4" /></svg>}
      <h3 className="heading-xs" style={{ marginTop: 18 }}>Sensitivity under declared perturbations</h3>
      {result.sensitivity.length ? <ul>{result.sensitivity.map((row, i) => <li key={i}>{String(row.parameter)}: stopping distance changes by {Number(row.stopping_distance_delta_m).toFixed(2)} m at {String(row.perturbation_value)} {String(row.perturbation_unit)} · helpful evidence: {String(row.reducing_observation)}</li>)}</ul> : <p className="text-sm">Sensitivity unavailable because the baseline does not identify the required parameters. Supply explicit scenario values and re-run after adding a supported sensitivity range.</p>}
      <details style={{ marginTop: 14 }}><summary>Assumptions and provenance</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{JSON.stringify(result.assumptions, null, 2)}</pre></details>
    </section>}
  </main>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div style={{ padding: 14, borderRadius: 10, background: "var(--bg-secondary)" }}><div className="text-xs">{label}</div><strong>{value}</strong></div>; }

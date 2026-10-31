"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { calibrationApi, jobsApi, phase4Api, tracksApi } from "@/lib/api";
import type { DynamicsRun, HomographyFit, TrackSummary } from "@/lib/api";

type Certificate = { status: string; interval_type: string; reason: string; condition?: string | null; improving_observation?: string | null };

export default function DynamicsPage({ params }: { params: { id: string; mediaId: string } }) {
  const { id: caseId, mediaId } = params;
  const [tracks, setTracks] = useState<TrackSummary[]>([]);
  const [fit, setFit] = useState<HomographyFit | null>(null);
  const [trackId, setTrackId] = useState("");
  const [result, setResult] = useState<DynamicsRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ts, f] = await Promise.all([tracksApi.list(caseId, mediaId), calibrationApi.getActiveFit(caseId, mediaId)]);
      setTracks(ts);
      setFit(f);
      const chosen = ts.find((t) => t.is_human_confirmed && t.category === "vehicle") ?? ts.find((t) => t.is_human_confirmed);
      if (chosen) setTrackId((old) => old || chosen.id);
      try { setResult(await phase4Api.getDynamics(caseId, mediaId)); } catch { setResult(null); }
    } catch (e) { setError((e as Error).message); }
  }, [caseId, mediaId]);
  useEffect(() => { void load(); }, [load]);

  const run = async () => {
    if (!trackId || !fit) return;
    setBusy(true); setError(null);
    try {
      const queued = await phase4Api.queueDynamics(caseId, mediaId, { track_id: trackId, calibration_fit_id: fit.id, seed: 42 });
      const deadline = Date.now() + 180000;
      while (Date.now() < deadline) {
        const job = await jobsApi.get(queued.job_id);
        if (job.status === "failed") throw new Error(job.error_message || "Dynamics job failed");
        if (job.status === "done") break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
      const current = await phase4Api.getDynamics(caseId, mediaId);
      setResult(current);
      if (current.status !== "done") setError(current.error_message || "Analysis did not complete; refresh to check its status.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  let certs: Record<string, Certificate> = {};
  try { certs = result?.certificates_json ? JSON.parse(result.certificates_json) : {}; } catch { /* malformed stored output is omitted */ }
  let points: Array<Record<string, number>> = [];
  try { points = result?.fitted_points_json ? JSON.parse(result.fitted_points_json) : []; } catch { /* malformed stored output is omitted */ }

  return <main className="page-content fade-in" style={{ maxWidth: 1100, margin: "0 auto" }}>
    <div className="page-header"><p><Link href={`/cases/${caseId}`}>Case</Link> / Media / Phase 4</p><h1>Dynamics report</h1><p>Track-only fit. This is an analysis under declared assumptions, not a legal fault finding.</p></div>
    {error && <div className="alert alert-error">{error}</div>}
    <section className="card card-body" style={{ marginBottom: 20 }}>
      <h2 className="heading-sm">Run calibrated motion fit</h2>
      <p className="text-sm">Select a reviewer-confirmed vehicle track. Testimony is not used in this fit.</p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
        <label className="form-label">Vehicle track<select className="form-input" value={trackId} onChange={(e) => setTrackId(e.target.value)}>
          <option value="">Select a confirmed track</option>{tracks.filter((t) => t.is_human_confirmed).map((t) => <option key={t.id} value={t.id}>{t.category} · {t.point_count} points · {t.id.slice(0, 8)}</option>)}
        </select></label>
        <span className="badge badge-neutral">{fit ? `Scale error ${(fit.scale_relative_error! * 100).toFixed(1)}% · homography RMSE ${fit.reprojection_rmse_px.toFixed(2)} px` : "Calibration required"}</span>
        <button className="btn btn-primary" disabled={!fit || !trackId || busy} onClick={() => void run()}>{busy ? "Fitting…" : "Run dynamics fit"}</button>
      </div>
      {tracks.length > 0 && !tracks.some((t) => t.is_human_confirmed) && <p className="text-sm">Confirm a vehicle track in the Tracks review page before fitting.</p>}
    </section>
    {result && <>
      <section className="card card-body" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}><div><h2 className="heading-sm">Run {result.run_id.slice(0, 10)}</h2><p className="text-sm">{result.model_name} v{result.model_version} · seed {result.seed} · {result.status}</p></div><span className="badge badge-neutral">{result.interval_type === "illustrative_range" ? "Illustrative range · coverage unvalidated" : result.interval_type}</span></div>
        {result.error_message && <p className="text-sm">{result.error_message}</p>}
        {result.status === "done" && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, marginTop: 16 }}>
          <Metric label="Entry speed" value={result.entry_speed_kmh == null ? "Not identifiable" : `${result.entry_speed_lo_kmh?.toFixed(1) ?? "?"}–${result.entry_speed_hi_kmh?.toFixed(1) ?? "?"} km/h`} />
          <Metric label="Deceleration" value={result.mean_decel_ms2 == null ? "Not identifiable" : `${result.mean_decel_lo_ms2?.toFixed(2) ?? "?"}–${result.mean_decel_hi_ms2?.toFixed(2) ?? "?"} m/s²`} />
          <Metric label="Braking onset" value={result.braking_onset_json ? "Change point detected · illustrative interval" : "Not identifiable"} />
        </div>}
      </section>
      {result.status === "done" && <section className="card card-body" style={{ marginBottom: 20 }}>
        <h2 className="heading-sm">Per-quantity identifiability certificates</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>{Object.entries(certs).map(([name, cert]) => <article key={name} style={{ border: "1px solid var(--border)", padding: 14, borderRadius: 10 }}><strong>{name.replaceAll("_", " ")}</strong><p><span className="badge badge-neutral">{cert.status}</span> <span className="text-xs">{cert.interval_type}</span></p><p className="text-sm">{cert.reason}</p>{cert.condition && <p className="text-xs">Condition: {cert.condition}</p>}{cert.improving_observation && <p className="text-xs">Helpful evidence: {cert.improving_observation}</p>}</article>)}</div>
      </section>}
      {points.length > 0 && <section className="card card-body" style={{ marginBottom: 20 }}><h2 className="heading-sm">Fitted trajectory samples</h2><p className="text-xs">Smoothed model output; raw track observations remain the source evidence.</p><div style={{ maxHeight: 320, overflow: "auto" }}><table className="table"><thead><tr><th>Frame</th><th>Time</th><th>Speed interval</th><th>Position uncertainty</th></tr></thead><tbody>{points.slice(0, 200).map((p, i) => <tr key={`${p.frame_index}-${i}`}><td>{p.frame_index}</td><td>{p.presentation_ts_s.toFixed(3)} s</td><td>{p.speed_lo_kmh.toFixed(1)}–{p.speed_hi_kmh.toFixed(1)} km/h</td><td>±{p.pos_sigma_x_m.toFixed(3)}, ±{p.pos_sigma_y_m.toFixed(3)} m</td></tr>)}</tbody></table></div></section>}
      {result.status === "done" && <nav style={{ display: "flex", gap: 12 }}><Link className="btn btn-secondary" href={`/cases/${caseId}/media/${mediaId}/simulate`}>Open illustrative simulator →</Link><Link className="btn btn-secondary" href={`/cases/${caseId}/media/${mediaId}/rivals`}>Search rival hypotheses →</Link></nav>}
    </>}
  </main>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div style={{ padding: 14, borderRadius: 10, background: "var(--bg-secondary)" }}><div className="text-xs">{label}</div><div className="heading-sm" style={{ marginTop: 6 }}>{value}</div></div>;
}

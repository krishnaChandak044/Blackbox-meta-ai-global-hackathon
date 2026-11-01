"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { phase4Api } from "@/lib/api";
import type { DynamicsRun, RivalResponse } from "@/lib/api";

export default function RivalsPage({ params }: { params: { id: string; mediaId: string } }) {
  const { id: caseId, mediaId } = params;
  const [baseline, setBaseline] = useState<DynamicsRun | null>(null);
  const [result, setResult] = useState<RivalResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    phase4Api.getDynamics(caseId, mediaId).then(setBaseline).catch((e) => setError((e as Error).message));
    phase4Api.getRivals(caseId, mediaId).then(setResult).catch(() => undefined);
  }, [caseId, mediaId]);
  const search = async () => {
    if (!baseline) return;
    setBusy(true); setError(null);
    try { setResult(await phase4Api.searchRivals(caseId, mediaId, { primary_run_id: baseline.run_id, seed: 42, grid_n: 15, acceptance_threshold_m: 1.0 })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <main className="page-content fade-in" style={{ maxWidth: 1000, margin: "0 auto" }}>
    <div className="page-header"><p><Link href={`/cases/${caseId}/media/${mediaId}/dynamics`}>Dynamics report</Link> / Rivals</p><h1>Rival hypothesis search</h1><p>Search a bounded parameter space for materially different motion histories that also fit the observed track.</p></div>
    {error && <div className="alert alert-error">{error}</div>}
    <div className="alert" style={{ background: "var(--sand-light)", padding: 14, borderRadius: 10, marginBottom: 16 }}><strong>Search is bounded.</strong> A rival found here is an alternative within the stated parameter ranges and residual threshold. No rival found does not prove there are no other explanations.</div>
    <section className="card card-body" style={{ marginBottom: 18 }}>
      <p className="text-sm">{baseline ? `Primary run ${baseline.run_id.slice(0, 10)} · ${baseline.model_name} v${baseline.model_version}` : "Run a dynamics fit first."}</p>
      <button className="btn btn-primary" disabled={!baseline || baseline.status !== "done" || busy} onClick={() => void search()}>{busy ? "Searching 3D parameter grid…" : "Search rival hypotheses"}</button>
      {result && <p className="text-xs">Bounds: {JSON.stringify((result.manifest as { bounds?: unknown }).bounds)} · {String((result.manifest as { n_candidates_evaluated?: unknown }).n_candidates_evaluated)} candidates · seed {String((result.manifest as { seed?: unknown }).seed)} · {String((result.manifest as { objective?: unknown }).objective)}</p>}
    </section>
    {result && <section className="card card-body">
      <h2 className="heading-sm">Search result</h2>
      {result.empty_search_message ? <p className="text-sm">{result.empty_search_message}</p> : <div style={{ display: "grid", gap: 12 }}>{result.rivals.map((item, i) => <article key={i} style={{ border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}><strong>Rival {String(item.rank)} · {String(item.disambiguation_status).replaceAll("_", " ")}</strong><span className="badge badge-neutral">Track residual {Number(item.residual).toFixed(3)} m</span></div>
        <p className="text-sm">Candidate parameters: {JSON.stringify(item.params)}</p>
        <p className="text-sm">Primary residual: {Number(item.primary_residual).toFixed(3)} m. {item.rejection_reason ? String(item.rejection_reason) : "No second view was supplied; this rival remains unresolved."}</p>
        {item.distinguishing_evidence != null && <p className="text-xs">Potentially useful evidence: {String(item.distinguishing_evidence)}</p>}
      </article>)}</div>}
      <p className="text-xs" style={{ marginTop: 14 }}>{result.second_view_notes}</p>
      <p className="text-xs">Search ID: {result.id}. All candidate and threshold details are saved with this search.</p>
    </section>}
  </main>;
}

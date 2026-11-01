"use client";

import { useCallback, useEffect, useState } from "react";
import {
  mediaApi,
  phase4Api,
  phase5Api,
  type AtlasResponse,
  type DynamicsRun,
  type SourceMedia,
} from "@/lib/api";

type RunOption = { media: SourceMedia; run: DynamicsRun };

export default function AtlasPanel({ caseId }: { caseId: string }) {
  const [aggregates, setAggregates] = useState<AtlasResponse | null>(null);
  const [runs, setRuns] = useState<RunOption[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [consentState, setConsentState] = useState<"unknown" | "opted_in" | "opted_out">("unknown");
  const [contributing, setContributing] = useState(false);
  const [savingConsent, setSavingConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [form, setForm] = useState({ cell: "", bucket: "", type: "crossing", pedestrians: "", cyclists: "", motorVehicles: "", conflictCount: "", ttc: "", p95: "" });

  const loadAggregates = useCallback(async () => {
    try { setAggregates(await phase5Api.atlasAggregates()); }
    catch (e) { setError((e as Error).message); }
  }, []);

  useEffect(() => {
    let alive = true;
    async function loadRuns() {
      try {
        const [media, consent] = await Promise.all([
          mediaApi.list(caseId), phase5Api.getAtlasConsent(caseId),
        ]);
        if (alive) setConsentState(consent.opted_in ? "opted_in" : "opted_out");
        const options = (await Promise.all(media.map(async (item) => {
          try {
            const run = await phase4Api.getDynamics(caseId, item.id);
            return run.status === "done" ? { media: item, run } : null;
          } catch { return null; }
        }))).filter((value): value is RunOption => value !== null);
        if (alive) {
          setRuns(options);
          if (options[0]) setSelectedRun((previous) => previous || options[0].run.run_id);
        }
      } catch (e) { if (alive) setError((e as Error).message); }
    }
    void loadRuns(); void loadAggregates();
    return () => { alive = false; };
  }, [caseId, loadAggregates]);

  const saveConsent = async (optedIn: boolean) => {
    setSavingConsent(true); setError(null); setNotice(null);
    try {
      const response = await phase5Api.setAtlasConsent(caseId, optedIn);
      setConsentState(response.opted_in ? "opted_in" : "opted_out");
      if (!response.opted_in) setContributing(false);
      setNotice(response.opted_in
        ? "This case opted into derived, coarse Atlas summaries. The source footage and narratives are never contributed."
        : "Atlas consent revoked. This case will be excluded from future aggregates.");
      await loadAggregates();
    } catch (e) { setError((e as Error).message); }
    finally { setSavingConsent(false); }
  };

  const addContribution = async () => {
    if (consentState !== "opted_in") { setError("Give separate Atlas consent before adding a case summary."); return; }
    if (!selectedRun || !form.cell || !form.bucket || !form.conflictCount) { setError("Choose a completed dynamics run and fill the coarse cell, quarter, and conflict count."); return; }
    setBusy(true); setError(null); setNotice(null);
    const roadUserMix: Record<string, number> = {};
    if (form.pedestrians) roadUserMix.pedestrian = Number(form.pedestrians);
    if (form.cyclists) roadUserMix.cyclist = Number(form.cyclists);
    if (form.motorVehicles) roadUserMix.motor_vehicle = Number(form.motorVehicles);
    if (!Object.keys(roadUserMix).length) roadUserMix.other = 1;
    const metrics: Record<string, number> = { conflict_count: Number(form.conflictCount) };
    if (form.ttc) metrics.minimum_ttc_s = Number(form.ttc);
    if (form.p95) metrics.p95_speed_kmh = Number(form.p95);
    try {
      const result = await phase5Api.addAtlasContribution(caseId, {
        source_run_id: selectedRun, coarse_cell: form.cell.trim().toLowerCase(), time_bucket: form.bucket,
        conflict_type: form.type as "crossing" | "rear_end" | "turning" | "merge" | "other",
        road_user_mix: roadUserMix, metrics, reviewer_confirmed: true,
      });
      setNotice(`Derived summary added (${result.contribution_id.slice(0, 8)}). It remains suppressed until the minimum cohort is reached.`);
      await loadAggregates();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const visibleAggregates = aggregates?.aggregates ?? [];
  return (
    <section aria-labelledby="atlas-heading">
      <div className="mb-4">
        <p className="eyebrow">Opt-in, aggregate, private</p>
        <h2 id="atlas-heading">Prevention Atlas</h2>
        <p className="text-sm text-secondary mt-2">Only reviewed derived counts and metrics can be contributed. No media, names, exact coordinates, or narratives are sent to this view.</p>
      </div>
      {error && <div className="alert alert-error mb-4" role="alert">{error}</div>}
      {notice && <div className="alert alert-info mb-4" role="status">{notice}</div>}

      <div className="card mb-5"><div className="card-body atlas-consent-row">
        <div><strong>Separate consent for this case</strong><p className="text-xs text-secondary mt-1">Current page state: {consentState.replaceAll("_", " ")}. Consent is independent of evidence processing and can be revoked.</p></div>
        <div className="flex gap-2 flex-wrap">
          <button className="btn btn-primary btn-sm" disabled={savingConsent || consentState === "opted_in"} onClick={() => void saveConsent(true)}>{savingConsent ? "Saving…" : "Opt in to Atlas"}</button>
          <button className="btn btn-secondary btn-sm" disabled={savingConsent || consentState === "opted_out"} onClick={() => void saveConsent(false)}>Revoke / opt out</button>
        </div>
      </div></div>

      {consentState === "opted_in" && <div className="card mb-5"><div className="card-body">
        <h3 className="heading-sm">Add one reviewer-confirmed summary</h3>
        <p className="text-xs text-secondary mt-1 mb-4">Use a coarse geohash cell of 4–5 characters (not an address or GPS coordinate) and a calendar quarter. One contribution per case/cell/period/type.</p>
        {runs.length === 0 ? <p className="text-sm text-secondary">A completed dynamics run is required before contributing.</p> : <>
          <div className="atlas-form-grid">
            <label className="form-label">Completed dynamics run<select className="form-input" value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}>{runs.map(({ media, run }) => <option value={run.run_id} key={run.run_id}>{media.original_filename} · {run.run_id.slice(0, 8)}</option>)}</select></label>
            <label className="form-label">Coarse cell<input className="form-input" maxLength={5} value={form.cell} onChange={(e) => setForm({ ...form, cell: e.target.value })} placeholder="e.g. u4pr" /></label>
            <label className="form-label">Time bucket<input className="form-input" value={form.bucket} onChange={(e) => setForm({ ...form, bucket: e.target.value })} placeholder="2026-Q4" /></label>
            <label className="form-label">Conflict type<select className="form-input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}><option value="crossing">Crossing</option><option value="rear_end">Rear end</option><option value="turning">Turning</option><option value="merge">Merge</option><option value="other">Other</option></select></label>
            <label className="form-label">Conflict count<input className="form-input" type="number" min="0" max="10000" value={form.conflictCount} onChange={(e) => setForm({ ...form, conflictCount: e.target.value })} /></label>
            <label className="form-label">Minimum TTC, seconds (optional)<input className="form-input" type="number" min="0" step="0.1" value={form.ttc} onChange={(e) => setForm({ ...form, ttc: e.target.value })} /></label>
            <label className="form-label">95th percentile speed, km/h (optional)<input className="form-input" type="number" min="0" max="500" step="0.1" value={form.p95} onChange={(e) => setForm({ ...form, p95: e.target.value })} /></label>
            <label className="form-label">Pedestrian count<input className="form-input" type="number" min="0" max="10000" value={form.pedestrians} onChange={(e) => setForm({ ...form, pedestrians: e.target.value })} /></label>
            <label className="form-label">Cyclist count<input className="form-input" type="number" min="0" max="10000" value={form.cyclists} onChange={(e) => setForm({ ...form, cyclists: e.target.value })} /></label>
            <label className="form-label">Motor vehicle count<input className="form-input" type="number" min="0" max="10000" value={form.motorVehicles} onChange={(e) => setForm({ ...form, motorVehicles: e.target.value })} /></label>
          </div>
          <label className="atlas-review-check"><input type="checkbox" checked={contributing} onChange={(e) => setContributing(e.target.checked)} /> I reviewed these derived values and confirm they are suitable for coarse aggregation.</label>
          <button className="btn btn-primary btn-sm mt-3" disabled={busy || !contributing} onClick={() => void addContribution()}>{busy ? "Adding…" : "Add reviewed summary"}</button>
        </>}
      </div></div>}

      <div className="flex items-center justify-between gap-3 mb-3"><div><h3 className="heading-sm">Qualified aggregates</h3><p className="text-xs text-secondary">Authenticated private analyst view. Groups below the case threshold are suppressed.</p></div><button className="btn btn-secondary btn-sm" onClick={() => void loadAggregates()}>Refresh</button></div>
      {aggregates && <div className="radar-summary mb-3"><span>Minimum group size: {aggregates.minimum_cohort}</span><span>Suppressed groups: {aggregates.suppressed_group_count}</span><span>{aggregates.access_scope}</span></div>}
      {visibleAggregates.length === 0 ? <div className="empty-state"><h3>No qualified groups yet</h3><p>Groups are withheld until enough distinct cases opt in. An empty map does not mean there are no incidents.</p></div> : <div className="atlas-grid">{visibleAggregates.map((item) => <article className="card atlas-card" key={`${item.coarse_cell}:${item.time_bucket}:${item.conflict_type}`}>
        <div className="card-body"><div className="flex items-center justify-between gap-2"><strong>{item.coarse_cell}</strong><span className="badge badge-neutral">{item.distinct_case_count} cases</span></div><p className="text-xs text-secondary mt-2">{item.time_bucket} · {item.conflict_type.replaceAll("_", " ")}</p><dl className="atlas-metrics">{Object.entries(item.mean_metrics).map(([name, value]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{value.toFixed(2)}</dd></div>)}</dl><p className="text-xs text-secondary mt-3">Descriptive aggregate only; not causal evidence or an engineering recommendation.</p></div>
      </article>)}</div>}
    </section>
  );
}

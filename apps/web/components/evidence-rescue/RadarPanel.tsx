"use client";

import { useCallback, useEffect, useState } from "react";
import {
  phase5Api,
  type EvidenceDraftInput,
  type EvidenceNeed,
  type EvidenceNeedsResponse,
} from "@/lib/api";

type SourceForm = {
  source: string;
  deadline: string;
  timezone: string;
  recipient: string;
  dateRange: string;
  timeRange: string;
};

const EMPTY_FORM: SourceForm = {
  source: "", deadline: "", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  recipient: "", dateRange: "", timeRange: "",
};

export default function RadarPanel({ caseId }: { caseId: string }) {
  const [data, setData] = useState<EvidenceNeedsResponse | null>(null);
  const [forms, setForms] = useState<Record<string, SourceForm>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await phase5Api.evidenceNeeds(caseId);
      setData(response);
      setForms((previous) => {
        const next = { ...previous };
        for (const need of response.needs) {
          if (next[need.id]) continue;
          const detail = need.verification ?? {};
          const deadline = typeof detail.retention_deadline === "string" ? detail.retention_deadline : "";
          next[need.id] = {
            ...EMPTY_FORM,
            source: typeof detail.source_description === "string" ? detail.source_description : "",
            timezone: typeof detail.timezone_name === "string" ? detail.timezone_name : EMPTY_FORM.timezone,
            deadline: deadline ? toDateTimeLocal(deadline) : "",
            recipient: typeof detail.contact_name === "string" ? detail.contact_name : "",
          };
        }
        return next;
      });
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => { void load(); }, [load]);

  const formFor = (need: EvidenceNeed) => forms[need.id] ?? EMPTY_FORM;
  const updateForm = (needId: string, patch: Partial<SourceForm>) => {
    setForms((previous) => ({
      ...previous,
      [needId]: { ...(previous[needId] ?? EMPTY_FORM), ...patch },
    }));
  };

  const verifySource = async (need: EvidenceNeed) => {
    const form = formFor(need);
    if (!form.source.trim()) {
      setError("Describe the source you personally verified before saving it.");
      return;
    }
    setBusyId(need.id); setError(null); setNotice(null);
    try {
      await phase5Api.updateEvidenceNeed(caseId, need.id, {
        state: "verified_source", verified: true, source_description: form.source.trim(),
        retention_deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
        timezone_name: form.deadline ? form.timezone : undefined,
      });
      setNotice("Source details saved as human-verified. No request was sent.");
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusyId(null); }
  };

  const makeDraft = async (need: EvidenceNeed) => {
    const form = formFor(need);
    const body: EvidenceDraftInput = {
      recipient: form.recipient.trim(),
      source_description: form.source.trim(),
      date_range: form.dateRange.trim(),
      time_range: form.timeRange.trim(),
    };
    if (!body.recipient || !body.source_description || !body.date_range || !body.time_range) {
      setError("Fill in recipient, verified source, date range, and time range to create a draft.");
      return;
    }
    setBusyId(need.id); setError(null); setNotice(null);
    try {
      const result = await phase5Api.draftEvidenceRequest(caseId, need.id, body);
      setDrafts((previous) => ({ ...previous, [need.id]: result.draft }));
      setNotice("Draft created for your review. It has not been sent.");
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusyId(null); }
  };

  const updateState = async (need: EvidenceNeed, state: "requested_by_user" | "received" | "unavailable" | "refused") => {
    const form = formFor(need);
    setBusyId(need.id); setError(null); setNotice(null);
    try {
      await phase5Api.updateEvidenceNeed(caseId, need.id, {
        state, verified: true, source_description: form.source.trim() || undefined,
        retention_deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
        timezone_name: form.deadline ? form.timezone : undefined,
      });
      setNotice(`Evidence status updated to “${state.replaceAll("_", " ")}`);
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusyId(null); }
  };

  return (
    <section aria-labelledby="radar-heading">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <p className="eyebrow">Evidence collection</p>
          <h2 id="radar-heading">Evidence Rescue Radar</h2>
          <p className="text-sm text-secondary mt-2">
            Suggestions are heuristics. Sources and retention deadlines remain unknown until a person verifies them.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => void load()} disabled={loading}>Refresh</button>
      </div>
      {error && <div className="alert alert-error mb-4" role="alert">{error}</div>}
      {notice && <div className="alert alert-info mb-4" role="status">{notice}</div>}
      {loading && <p className="text-sm text-secondary">Loading evidence needs…</p>}
      {!loading && data && (
        <>
          {!data.analysis_run_id && <div className="alert alert-info mb-4" role="status">
            No completed calibrated dynamics run is available for this case. Speed and braking measurements are not produced; the radar is prioritizing evidence needed to establish metric scale.
          </div>}
          <div className="radar-summary mb-4">
            <span>{data.needs.length} candidate{data.needs.length === 1 ? "" : "s"}</span>
            <span>{data.ranking_note}</span>
            <span>Retention deadline: {data.retention_deadline_default}</span>
          </div>
          {data.needs.length === 0 ? (
            <div className="empty-state"><h3>No unresolved evidence needs returned</h3><p>That does not establish that all evidence is complete.</p></div>
          ) : (
            <div className="radar-list">
              {data.needs.map((need) => <NeedCard
                key={need.id} need={need} form={formFor(need)} draft={drafts[need.id] ?? need.draft_text ?? undefined}
                busy={busyId === need.id} onForm={(patch) => updateForm(need.id, patch)}
                onVerify={() => void verifySource(need)} onDraft={() => void makeDraft(need)}
                onState={(state) => void updateState(need, state)}
              />)}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function NeedCard({
  need, form, draft, busy, onForm, onVerify, onDraft, onState,
}: {
  need: EvidenceNeed; form: SourceForm; draft?: string; busy: boolean;
  onForm: (patch: Partial<SourceForm>) => void;
  onVerify: () => void; onDraft: () => void;
  onState: (state: "requested_by_user" | "received" | "unavailable" | "refused") => void;
}) {
  const verified = need.availability === "human_verified_source" || need.verification?.verified === true;
  return (
    <article className="card radar-card">
      <div className="card-body">
        <div className="radar-card-head">
          <div>
            <span className="badge badge-sand">{need.state.replaceAll("_", " ")}</span>
            <h3 className="heading-sm mt-2">{need.title}</h3>
          </div>
          <span className="radar-priority">Rank score {need.priority_score.toFixed(2)}</span>
        </div>
        <p className="text-sm mt-2">{need.ranking_basis}</p>
        <p className="text-xs text-secondary mt-2">
          Heuristic reduction index {need.heuristic_expected_reduction_fraction.toFixed(2)} · effort {need.effort_score_1_low_5_high.toFixed(1)} · privacy cost {need.privacy_cost_1_low_5_high.toFixed(1)}
        </p>
        <p className="text-xs text-secondary mt-1">Availability: {verified ? "human-verified" : "unknown"} · Retention deadline: {need.retention_deadline ? `${need.retention_deadline.hours_remaining.toFixed(1)} hours (verified)` : "unknown"}</p>
        <label className="form-label mt-4">Source you personally verified
          <input className="form-input" value={form.source} maxLength={500} onChange={(e) => onForm({ source: e.target.value })} placeholder="e.g. Store manager confirmed the camera covering the east entrance" />
        </label>
        <div className="radar-form-grid">
          <label className="form-label">Verified retention deadline (optional)
            <input className="form-input" type="datetime-local" value={form.deadline} onChange={(e) => onForm({ deadline: e.target.value })} />
          </label>
          <label className="form-label">Timezone for deadline
            <input className="form-input" value={form.timezone} onChange={(e) => onForm({ timezone: e.target.value })} placeholder="Asia/Kolkata" />
          </label>
        </div>
        <div className="flex gap-2 flex-wrap mt-3">
          <button className="btn btn-secondary btn-sm" disabled={busy} onClick={onVerify}>{busy ? "Saving…" : "Save verified source"}</button>
          {verified && <>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onState("requested_by_user")}>Mark requested</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onState("received")}>Mark received</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onState("unavailable")}>Unavailable</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onState("refused")}>Refused</button>
          </>}
        </div>
        {verified && <div className="radar-request-fields mt-4">
          <h4>Preservation request draft</h4>
          <p className="text-xs text-secondary">This creates text for you to review. Blackbox does not send it.</p>
          <div className="radar-form-grid">
            <label className="form-label">Recipient<input className="form-input" maxLength={200} value={form.recipient} onChange={(e) => onForm({ recipient: e.target.value })} placeholder="Person or organization you identified" /></label>
            <label className="form-label">Date range<input className="form-input" maxLength={120} value={form.dateRange} onChange={(e) => onForm({ dateRange: e.target.value })} placeholder="Date or date range" /></label>
            <label className="form-label">Time range<input className="form-input" maxLength={120} value={form.timeRange} onChange={(e) => onForm({ timeRange: e.target.value })} placeholder="Approximate time window" /></label>
          </div>
          <button className="btn btn-primary btn-sm mt-3" disabled={busy} onClick={onDraft}>Create unsent draft</button>
        </div>}
        {draft && <pre className="preservation-draft mt-4" aria-label="Unsent preservation request draft">{draft}</pre>}
      </div>
    </article>
  );
}

function toDateTimeLocal(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

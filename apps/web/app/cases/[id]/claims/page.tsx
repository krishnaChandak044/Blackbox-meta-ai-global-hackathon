"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { claimsApi, jobsApi, transcriptsApi } from "@/lib/api";
import type { ClaimVerdict, TranscriptClaim } from "@/lib/api";

const COLUMNS = [
  { key: "unverified", label: "Needs review", background: "#f3eee3" },
  { key: "supported", label: "Supported", background: "#e8eee8" },
  { key: "contradicted", label: "Contradicted", background: "#f5e9e6" },
  { key: "inconclusive", label: "Inconclusive", background: "#efedf1" },
] as const;

function belongsInColumn(key: (typeof COLUMNS)[number]["key"], verdict?: ClaimVerdict) {
  if (key === "unverified") return !verdict;
  if (key === "inconclusive") return ["inconclusive", "insufficient_data"].includes(verdict?.verdict ?? "");
  return verdict?.verdict === key;
}

export default function ClaimsPage() {
  const { id } = useParams<{ id: string }>();
  const [claims, setClaims] = useState<TranscriptClaim[]>([]);
  const [verdicts, setVerdicts] = useState<Record<string, ClaimVerdict>>({});
  const [transcripts, setTranscripts] = useState<{ id: string; transcription_model: string }[]>([]);
  const [selected, setSelected] = useState<TranscriptClaim | null>(null);
  const [selectedVerdict, setSelectedVerdict] = useState<ClaimVerdict | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextClaims, nextTranscripts] = await Promise.all([claimsApi.list(id), transcriptsApi.list(id)]);
      setClaims(nextClaims);
      setTranscripts(nextTranscripts);
      const entries = await Promise.all(nextClaims.map(async (claim) => [claim.id, await claimsApi.getCheck(id, claim.id)] as const));
      const nextVerdicts: Record<string, ClaimVerdict> = {};
      for (const [claimId, verdict] of entries) if (verdict) nextVerdicts[claimId] = verdict;
      setVerdicts(nextVerdicts);
      setError(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void refresh(); }, [refresh]);

  const waitForJob = async (jobId: string) => {
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
      const job = await jobsApi.get(jobId);
      if (job.status === "done") return;
      if (job.status === "failed") throw new Error(job.error_message || "Claim extraction failed.");
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    throw new Error("Claim extraction is still running. Refresh this board in a moment.");
  };

  const extractClaims = async (transcriptId: string) => {
    setBusy(transcriptId); setError(null);
    try {
      const { job_id } = await claimsApi.extract(id, transcriptId);
      await waitForJob(job_id);
      await refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const openClaim = async (claim: TranscriptClaim) => {
    setSelected(claim); setSelectedVerdict(null); setError(null);
    try { setSelectedVerdict(await claimsApi.getCheck(id, claim.id)); }
    catch (reason) { setError((reason as Error).message); }
  };

  const runCheck = async () => {
    if (!selected) return;
    setBusy(selected.id); setError(null);
    try {
      const verdict = await claimsApi.check(id, selected.id);
      setSelectedVerdict(verdict);
      setVerdicts((previous) => ({ ...previous, [selected.id]: verdict }));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!selected) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setSelected(null); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selected]);

  return (
    <div className="main-with-sidebar">
      <aside className="sidebar">
        <Link href="/" className="sidebar-logo brand-lockup"><span className="brand-mark">B</span><span><strong>Blackbox</strong><small>Evidence workspace</small></span></Link>
        <nav className="sidebar-nav" aria-label="Case navigation">
          <div className="sidebar-section-label">Workspace</div>
          <Link href="/cases" className="nav-item">Cases</Link>
          <div className="sidebar-section-label">This case</div>
          <Link href={`/cases/${id}`} className="nav-item">Overview</Link>
          <Link href={`/cases/${id}/review-workspace`} className="nav-item">Review footage</Link>
          <Link href={`/cases/${id}/transcripts`} className="nav-item">Transcripts</Link>
          <Link href={`/cases/${id}/claims`} className="nav-item active" aria-current="page">Claims</Link>
          <Link href={`/cases/${id}/reports`} className="nav-item">Evidence &amp; reports</Link>
        </nav>
        <div className="sidebar-footer">Human review stays in control</div>
      </aside>

      <main className="page-content claims-page fade-in">
        <div className="phase5-nav"><Link href={`/cases/${id}`}>← Back to case</Link><span>Evidence review</span></div>
        <header className="page-header">
          <p className="eyebrow">Case review · Statements</p>
          <h1>Review claims</h1>
          <p>Check each extracted statement against available evidence. A result is a review aid, not a finding of fault.</p>
        </header>

        <section className="card" aria-label="Extract claims from a transcript">
          <div className="card-header"><div><h2 style={{ fontSize: 18, margin: 0 }}>Prepare claims</h2><p className="text-sm text-secondary" style={{ marginTop: 4 }}>Choose a transcript to identify checkable statements.</p></div></div>
          <div className="claims-toolbar">
            <span className="claims-toolbar-label">Transcript source</span>
            {transcripts.length ? transcripts.map((transcript) => <button key={transcript.id} className="btn btn-secondary btn-sm" disabled={Boolean(busy)} onClick={() => void extractClaims(transcript.id)}>{busy === transcript.id ? "Extracting claims…" : `Extract from ${transcript.transcription_model}`}</button>) : <span className="text-sm text-secondary">Add a transcript first to prepare claims.</span>}
            {!transcripts.length && <Link className="btn btn-primary btn-sm" href={`/cases/${id}/transcripts`}>Open transcripts</Link>}
          </div>
        </section>

        {error && <div className="alert alert-error" role="alert" style={{ marginTop: 18 }}>{error}<button className="btn btn-ghost btn-sm" onClick={() => setError(null)}>Dismiss</button></div>}
        {loading ? <div className="case-loading"><span className="spinner" /> Loading claims…</div> : <section className="claims-layout" aria-label="Claims by review status" style={{ marginTop: 22 }}>
          {COLUMNS.map((column) => {
            const items = claims.filter((claim) => belongsInColumn(column.key, verdicts[claim.id]));
            return <section className="claim-column" key={column.key} style={{ background: column.background }} aria-label={`${column.label}: ${items.length}`}>
              <header className="claim-column-head"><span>{column.label}</span><span className="badge badge-neutral">{items.length}</span></header>
              <div className="claim-column-list">
                {items.map((claim) => <button className="claim-card" key={claim.id} onClick={() => void openClaim(claim)} aria-label={`Review claim: ${claim.raw_text}`}>
                  <p>{claim.raw_text}</p>
                  <span className="claim-tags">{claim.assertions.map((assertion, index) => <span className="claim-tag" key={`${assertion.assertion_type}-${index}`}>{assertion.assertion_type}</span>)}</span>
                </button>)}
                {!items.length && <p className="claims-empty">{claims.length ? "No claims in this group." : "No claims yet. Add a transcript, then extract claims."}</p>}
              </div>
            </section>;
          })}
        </section>}
      </main>

      {selected && <div className="claim-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
        <section className="card claim-panel" role="dialog" aria-modal="true" aria-labelledby="claim-detail-title">
          <header className="claim-panel-head"><div><p className="eyebrow">Evidence-linked statement</p><h2 id="claim-detail-title" style={{ fontSize: 21, margin: 0 }}>Claim review</h2></div><button className="btn btn-secondary btn-sm" onClick={() => setSelected(null)} aria-label="Close claim review">Close</button></header>
          <div className="claim-panel-body">
            <p className="claim-statement">{selected.raw_text}</p>
            <section><h3 style={{ fontSize: 16, marginBottom: 10 }}>Current assessment</h3>
              {selectedVerdict ? <div className="claim-verdict" style={{ background: selectedVerdict.verdict === "supported" ? "#e8eee8" : selectedVerdict.verdict === "contradicted" ? "#f5e9e6" : "#efedf1" }}><span className={`badge ${selectedVerdict.verdict === "supported" ? "badge-sage" : selectedVerdict.verdict === "contradicted" ? "badge-rose" : "badge-lavender"}`}>{selectedVerdict.verdict.replaceAll("_", " ")}</span><p>{selectedVerdict.explanation}</p></div> : <p className="text-sm text-secondary">This statement has not been checked yet.</p>}
            </section>
            <section><h3 style={{ fontSize: 16, marginBottom: 8 }}>Check against the evidence</h3><p className="text-sm text-secondary" style={{ marginBottom: 14 }}>The system compares the claim with available case evidence. Review the cited material before relying on the result.</p><button className="btn btn-primary" onClick={() => void runCheck()} disabled={Boolean(busy)}>{busy === selected.id ? "Checking evidence…" : selectedVerdict ? "Run check again" : "Check this claim"}</button></section>
          </div>
        </section>
      </div>}
    </div>
  );
}

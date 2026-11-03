"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { jobsApi, mediaApi, transcriptsApi } from "@/lib/api";
import type { DiarisedSegment, SourceMedia, Transcript } from "@/lib/api";

const SPEAKER_COLORS: Record<string, string> = { witness_1: "#345d49", driver: "#476c77", officer: "#8d692f" };

export default function TranscriptsPage() {
  const { id } = useParams<{ id: string }>();
  const [media, setMedia] = useState<SourceMedia[]>([]);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyMediaId, setBusyMediaId] = useState<string | null>(null);
  const [manualText, setManualText] = useState("");
  const [savingManual, setSavingManual] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextMedia, nextTranscripts] = await Promise.all([mediaApi.list(id), transcriptsApi.list(id)]);
      setMedia(nextMedia); setTranscripts(nextTranscripts);
      setSelectedId((current) => current && nextTranscripts.some((item) => item.id === current) ? current : nextTranscripts[0]?.id ?? null);
      setError(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void refresh(); }, [refresh]);

  const selected = transcripts.find((item) => item.id === selectedId) ?? null;
  const activeMedia = media.find((item) => item.id === selected?.media_id) ?? media[0] ?? null;
  const segments = useMemo<DiarisedSegment[]>(() => {
    if (!selected?.diarised_json) return [];
    try { return JSON.parse(selected.diarised_json) as DiarisedSegment[]; }
    catch { return []; }
  }, [selected]);

  const transcribe = async (mediaId: string) => {
    setBusyMediaId(mediaId); setError(null);
    try {
      const { job_id } = await transcriptsApi.transcribe(id, mediaId);
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        const job = await jobsApi.get(job_id);
        if (job.status === "done") { await refresh(); return; }
        if (job.status === "failed") throw new Error(job.error_message || "Transcription failed.");
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
      throw new Error("Transcription is still running. Refresh this page in a moment.");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusyMediaId(null);
    }
  };

  const saveManualTranscript = async () => {
    if (!manualText.trim()) return;
    setSavingManual(true); setError(null);
    try {
      await transcriptsApi.create(id, { raw_text: manualText.trim() });
      setManualText(""); await refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSavingManual(false);
    }
  };

  const seekTo = (time: number) => {
    if (videoRef.current) videoRef.current.currentTime = time;
    setCurrentTime(time);
  };

  return (
    <div className="main-with-sidebar">
      <aside className="sidebar">
        <Link href="/" className="sidebar-logo brand-lockup"><span className="brand-mark">B</span><span><strong>Blackbox</strong><small>Evidence workspace</small></span></Link>
        <nav className="sidebar-nav" aria-label="Case navigation">
          <div className="sidebar-section-label">Workspace</div><Link href="/cases" className="nav-item">Cases</Link>
          <div className="sidebar-section-label">This case</div>
          <Link href={`/cases/${id}`} className="nav-item">Overview</Link>
          <Link href={`/cases/${id}/review-workspace`} className="nav-item">Review footage</Link>
          <Link href={`/cases/${id}/transcripts`} className="nav-item active" aria-current="page">Transcripts</Link>
          <Link href={`/cases/${id}/claims`} className="nav-item">Claims</Link>
          <Link href={`/cases/${id}/reports`} className="nav-item">Evidence &amp; reports</Link>
        </nav>
        <div className="sidebar-footer">Human review stays in control</div>
      </aside>

      <main className="page-content transcripts-page fade-in">
        <div className="phase5-nav"><Link href={`/cases/${id}`}>← Back to case</Link><Link href={`/cases/${id}/claims`}>Review claims →</Link></div>
        <header className="page-header"><p className="eyebrow">Case review · Spoken statements</p><h1>Transcripts</h1><p>Transcribe speech from a source clip or add a statement manually. Transcript text remains linked to its source.</p></header>
        {error && <div className="alert alert-error" role="alert">{error}<button className="btn btn-ghost btn-sm" onClick={() => setError(null)}>Dismiss</button></div>}

        {loading ? <div className="case-loading"><span className="spinner" /> Loading transcripts…</div> : <div className="transcripts-layout">
          <div className="transcript-column">
            {activeMedia ? <section className="card" aria-label="Source video">
              <div className="card-header"><div><h2 style={{ fontSize: 18, margin: 0 }}>Source recording</h2><p className="text-sm text-secondary" style={{ marginTop: 3 }}>Playback follows the selected transcript when it came from a clip.</p></div></div>
              <video ref={videoRef} src={mediaApi.streamUrl(id, activeMedia.id)} controls preload="metadata" className="transcript-video" onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)} />
              <div className="transcript-video-meta">{activeMedia.original_filename} · {currentTime.toFixed(2)} seconds</div>
            </section> : <section className="card card-body"><h2 style={{ fontSize: 18 }}>No source clips yet</h2><p className="text-sm text-secondary" style={{ margin: "6px 0 0" }}>Upload footage on the case overview to create source-linked transcripts.</p><Link href={`/cases/${id}`} className="btn btn-secondary" style={{ marginTop: 16 }}>Open case overview</Link></section>}

            <section className="card">
              <div className="card-header"><div><h2 style={{ fontSize: 18, margin: 0 }}>Transcribe a clip</h2><p className="text-sm text-secondary" style={{ marginTop: 3 }}>Speech recognition may make mistakes; review the result against the recording.</p></div></div>
              <div className="card-body" style={{ display: "grid", gap: 10 }}>
                {media.length ? media.map((item) => <div className="transcript-source-row" key={item.id}><span className="transcript-source-name">{item.original_filename}</span><button className="btn btn-secondary btn-sm" disabled={Boolean(busyMediaId)} onClick={() => void transcribe(item.id)}>{busyMediaId === item.id ? "Transcribing…" : "Create transcript"}</button></div>) : <p className="text-sm text-secondary">Upload a video clip before using automatic transcription.</p>}
                <div className="divider" />
                <label className="form-label" htmlFor="manual-transcript">Add a transcript manually</label>
                <textarea id="manual-transcript" className="form-textarea" value={manualText} onChange={(event) => setManualText(event.target.value)} placeholder="Paste or type a statement. Include who is speaking if known." />
                <button className="btn btn-primary" disabled={!manualText.trim() || savingManual} onClick={() => void saveManualTranscript()}>{savingManual ? "Saving transcript…" : "Save manual transcript"}</button>
              </div>
            </section>
          </div>

          <div className="transcript-column">
            {!transcripts.length ? <section className="card empty-state"><div className="empty-state-icon" aria-hidden="true">T</div><h2 style={{ fontSize: 20 }}>No transcripts yet</h2><p>Create one from a clip or add a statement manually. Your transcript will appear here for review.</p></section> : <>
              <section className="card" aria-label="Saved transcripts"><div className="card-header"><div><h2 style={{ fontSize: 18, margin: 0 }}>Saved statements</h2><p className="text-sm text-secondary" style={{ marginTop: 3 }}>{transcripts.length} transcript{transcripts.length === 1 ? "" : "s"}</p></div></div>
                <div className="transcript-tabs">{transcripts.map((item) => <button key={item.id} className={`btn transcript-tab ${selectedId === item.id ? "btn-primary" : "btn-secondary"}`} onClick={() => setSelectedId(item.id)} aria-pressed={selectedId === item.id}>{item.transcription_model} · {item.word_count} words</button>)}</div>
              </section>
              {selected && <section className="card">
                <div className="card-header" style={{ justifyContent: "space-between" }}><div><h2 style={{ fontSize: 18, margin: 0 }}>{selected.transcription_model}</h2><p className="text-sm text-secondary" style={{ marginTop: 3 }}>Statement text · {selected.word_count} words</p></div><span className="badge badge-neutral">{selected.word_count} words</span></div>
                <div className="card-body"><p className="transcript-text">{selected.raw_text}</p></div>
                {segments.length > 0 && <div aria-label="Timestamped speaker segments">{segments.map((segment, index) => {
                  const active = currentTime >= segment.start && currentTime <= segment.end;
                  return <button className="transcript-segment" key={`${segment.start}-${index}`} onClick={() => seekTo(segment.start)} aria-label={`Play from ${segment.start.toFixed(1)} seconds, ${segment.speaker}`} aria-current={active ? "true" : undefined} style={{ width: "100%", border: 0, textAlign: "left", background: active ? "#e8eee8" : "transparent" }}>
                    <span className="speaker-tag" style={{ background: SPEAKER_COLORS[segment.speaker] ?? "#697168" }}>{segment.speaker.replaceAll("_", " ")}</span><span>{segment.text}<small style={{ display: "block", marginTop: 5, color: "#737b72" }}>{segment.start.toFixed(1)}–{segment.end.toFixed(1)} s · Select to play this moment</small></span>
                  </button>;
                })}</div>}
              </section>}
            </>}
          </div>
        </div>}
      </main>
    </div>
  );
}

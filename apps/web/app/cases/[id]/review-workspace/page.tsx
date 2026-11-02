"use client";

import Link from "next/link";
import Image from "next/image";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { mediaApi, reviewWorkspaceApi, type AcousticAnalysis, type FrameAnnotation, type ReviewMedia, type ReviewWorkspace } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const V1 = `${API}/api/v1`;

export default function ReviewWorkspacePage() {
  const { id: caseId } = useParams<{ id: string }>();
  const [workspace, setWorkspace] = useState<ReviewWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [commonTime, setCommonTime] = useState(0);
  const [offsets, setOffsets] = useState<Record<string, number>>({});
  const [uncertainties, setUncertainties] = useState<Record<string, number>>({});
  const [bases, setBases] = useState<Record<string, string>>({});
  const [anchorSource, setAnchorSource] = useState<Record<string, number | null>>({});
  const [anchorReference, setAnchorReference] = useState<Record<string, number | null>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [analysis, setAnalysis] = useState<Record<string, AcousticAnalysis>>({});
  const [annotationMediaId, setAnnotationMediaId] = useState("");
  const [annotationKind, setAnnotationKind] = useState<"event" | "signal_state" | "stop_line" | "ground_contact" | "occlusion_boundary" | "road_condition" | "note">("event");
  const [annotationLabel, setAnnotationLabel] = useState("");
  const [annotationNote, setAnnotationNote] = useState("");
  const [annotationKey, setAnnotationKey] = useState("");
  const [frozenFrame, setFrozenFrame] = useState("");
  const [frameTime, setFrameTime] = useState(0);
  const [frameIndex, setFrameIndex] = useState(0);
  const [pendingFrameSeek, setPendingFrameSeek] = useState<number | null>(null);
  const [imagePoint, setImagePoint] = useState<{ x: number; y: number } | null>(null);
  const videos = useRef<Record<string, HTMLVideoElement | null>>({});
  const annotationVideo = useRef<HTMLVideoElement | null>(null);
  const leader = useRef("");

  const load = useCallback(async () => {
    try {
      const result = await reviewWorkspaceApi.get(caseId);
      setWorkspace(result);
      setAnalysis(Object.fromEntries(result.acoustic_analyses.map((item) => [item.media_id, item])));
      const initial: Record<string, number> = {};
      const uncertainty: Record<string, number> = {};
      const basis: Record<string, string> = {};
      for (const [index, clip] of result.media.entries()) {
        initial[clip.id] = clip.sync?.offset_seconds ?? 0;
        uncertainty[clip.id] = clip.sync?.uncertainty_seconds ?? 0.5;
        basis[clip.id] = clip.sync?.alignment_basis ?? (index === 0 ? "Reference clip; establishes the case review timeline." : "");
      }
      setOffsets(initial); setUncertainties(uncertainty); setBases(basis);
      setAnnotationMediaId(result.media[0]?.id ?? "");
      setError("");
    } catch (reason) { setError((reason as Error).message); }
    finally { setLoading(false); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  const reference = workspace?.media[0];
  const annotations = useMemo(() => [...(workspace?.annotations ?? [])].sort((a, b) => a.timestamp_seconds - b.timestamp_seconds), [workspace]);
  const duration = useMemo(() => Math.max(0, ...(workspace?.media.map((clip) => (clip.duration_seconds ?? 0) + (offsets[clip.id] ?? 0)) ?? [0])), [workspace, offsets]);

  const seekAll = (time: number, sourceMediaId?: string, sourceLocalTime?: number) => {
    setCommonTime(Math.max(0, time));
    const source = workspace?.media.find((clip) => clip.id === sourceMediaId);
    const sourceIsAligned = !sourceMediaId || sourceMediaId === reference?.id || !!source?.sync;
    for (const clip of workspace?.media ?? []) {
      const video = videos.current[clip.id];
      if (sourceMediaId && !sourceIsAligned && clip.id !== sourceMediaId) continue;
      if (clip.id !== sourceMediaId && clip.id !== reference?.id && !clip.sync) continue;
      if (!video || !Number.isFinite(video.duration) || video.readyState < 1) continue;
      const local = clip.id === sourceMediaId && sourceLocalTime != null ? sourceLocalTime : time - (offsets[clip.id] ?? 0);
      if (local >= 0 && local <= video.duration && Math.abs(video.currentTime - local) > 0.12) video.currentTime = local;
    }
  };

  const saveOffset = async (clip: ReviewMedia, index: number) => {
    const ref = reference;
    if (!ref) return;
    const offset = index === 0 ? 0 : offsets[clip.id] ?? 0;
    setBusy((old) => ({ ...old, [`sync-${clip.id}`]: true })); setError("");
    try {
      const saved = await reviewWorkspaceApi.saveSync(caseId, clip.id, {
        reference_media_id: ref.id,
        offset_seconds: offset,
        uncertainty_seconds: index === 0 ? 0 : uncertainties[clip.id] ?? 0.5,
        alignment_basis: bases[clip.id]?.trim() || (index === 0 ? "Reference clip; establishes the case review timeline." : ""),
        source_anchor_seconds: index === 0 ? null : anchorSource[clip.id] ?? null,
        reference_anchor_seconds: index === 0 ? null : anchorReference[clip.id] ?? null,
      });
      setWorkspace((old) => old ? { ...old, media: old.media.map((item) => item.id === clip.id ? { ...item, sync: saved } : item) } : old);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy((old) => ({ ...old, [`sync-${clip.id}`]: false })); }
  };

  const analyze = async (clip: ReviewMedia) => {
    setBusy((old) => ({ ...old, [`audio-${clip.id}`]: true })); setError("");
    try {
      const result = await reviewWorkspaceApi.analyzeAudio(caseId, clip.id);
      setAnalysis((old) => ({ ...old, [clip.id]: result }));
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy((old) => ({ ...old, [`audio-${clip.id}`]: false })); }
  };

  const freezeFrame = () => {
    const video = annotationVideo.current;
    if (!video || !video.videoWidth || !video.videoHeight) { setError("Wait for the selected video to load, then freeze its current frame."); return; }
    for (const item of workspace?.media ?? []) videos.current[item.id]?.pause();
    const canvas = document.createElement("canvas"); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) { setError("This browser could not capture the displayed frame."); return; }
    try {
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      setFrozenFrame(canvas.toDataURL("image/jpeg", 0.92));
    } catch {
      setError("The browser could not read this video frame for annotation. Check the API CORS settings, then reload the clip.");
      return;
    }
    setFrameTime(video.currentTime);
    const clip = workspace?.media.find((item) => item.id === annotationMediaId);
    setFrameIndex(Math.round(video.currentTime * (clip?.fps_nominal || 30)));
    setImagePoint(null); setError("");
  };

  const saveAnnotation = async () => {
    if (!annotationLabel.trim()) { setError("Add a short label before saving the frame annotation."); return; }
    setBusy((old) => ({ ...old, annotation: true })); setError("");
    try {
      const item = await reviewWorkspaceApi.addAnnotation(caseId, {
        annotation_key: annotationKey || null, media_id: annotationMediaId, kind: annotationKind,
        label: annotationLabel, note: annotationNote, timestamp_seconds: frameTime, frame_index: frameIndex,
        x_normalized: imagePoint?.x ?? null, y_normalized: imagePoint?.y ?? null,
      });
      setWorkspace((old) => old ? { ...old, annotations: [...old.annotations, item] } : old);
      setAnnotationKey(""); setAnnotationLabel(""); setAnnotationNote("");
      setFrozenFrame(""); setImagePoint(null);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy((old) => ({ ...old, annotation: false })); }
  };

  const beginCorrection = (item: FrameAnnotation) => {
    setAnnotationKey(item.annotation_key); setAnnotationMediaId(item.media_id);
    setAnnotationKind(item.kind as typeof annotationKind); setAnnotationLabel(item.label); setAnnotationNote(item.note);
    const clip = workspace?.media.find((entry) => entry.id === item.media_id);
    if (annotationMediaId === item.media_id && annotationVideo.current) annotationVideo.current.currentTime = item.timestamp_seconds;
    else setPendingFrameSeek(item.timestamp_seconds);
    if (clip) setFrameIndex(item.frame_index);
    setError("Re-freeze the source frame to create a new version. Previous annotation versions remain in history.");
    setFrozenFrame("");
  };

  if (loading) return <main className="page-content"><div className="spinner" /> Loading review tools…</main>;
  if (!workspace) return <main className="page-content"><div className="alert alert-error">{error || "Could not load this case."}</div></main>;

  const versions = new Map<string, FrameAnnotation[]>();
  for (const item of annotations) versions.set(item.annotation_key, [...(versions.get(item.annotation_key) ?? []), item]);

  return <main className="page-content review-workspace fade-in">
    <div className="phase5-nav"><Link href={`/cases/${caseId}`}>← Back to case</Link><Link href={`/cases/${caseId}/phase5`}>Evidence &amp; exports →</Link></div>
    <header className="page-header"><p className="eyebrow">Evidence review · Original clips</p><h1>Synchronized review workspace</h1>
      <p>Compare up to three source clips, inspect audio transient candidates, and add versioned notes to exact frames. Time offsets are reviewer estimates and retain their uncertainty.</p>
    </header>
    {error && <div className="alert alert-error" role="alert">{error}<button className="btn btn-ghost btn-sm" onClick={() => setError("")}>Dismiss</button></div>}
    {!workspace.media.length && <div className="card card-body">Upload a clip to this case before opening the review workspace.</div>}
    {workspace.media.length > 0 && <>
      <section className="card card-body review-sync-section">
        <div className="review-section-title"><div><p className="eyebrow">Feature 1 · Multi-camera review</p><h2>Review the clips on one timeline</h2>
          <p>{workspace.sync_semantics}. Set an offset only when you can identify a matching event in both clips.</p></div>
          <div className="review-common-time">Shared time <strong>{commonTime.toFixed(2)} s</strong></div></div>
        <label className="review-timebar">Shared review time <input type="range" min="0" max={Math.max(0.1, duration)} step="0.01" value={Math.min(commonTime, Math.max(0.1, duration))} onChange={(event) => seekAll(Number(event.target.value))} /><span>{Math.min(commonTime, duration).toFixed(2)} / {duration.toFixed(2)} s</span></label>
        <div className="review-clips-grid">
          {workspace.media.map((clip, index) => {
            const localTime = commonTime - (offsets[clip.id] ?? 0);
            const inCoverage = localTime >= 0 && (clip.duration_seconds == null || localTime <= clip.duration_seconds);
            return <article className="review-clip-card" key={clip.id}>
              <h3>{index === 0 ? "Reference clip" : `Clip ${index + 1}`} <small>{clip.filename}</small></h3>
            {inCoverage ? <video ref={(node) => { videos.current[clip.id] = node; }} src={mediaApi.streamUrl(caseId, clip.id)} controls preload="metadata" onLoadedMetadata={(event) => { const video = event.currentTarget; if (clip.id !== reference?.id && !clip.sync) return; const start = commonTime - (offsets[clip.id] ?? 0); if (start >= 0 && start <= video.duration) video.currentTime = start; }} onPlay={(event) => {
                const isAligned = clip.id === reference?.id || !!clip.sync;
                leader.current = isAligned ? clip.id : "";
                const video = event.currentTarget;
                for (const other of workspace.media) {
                  const peer = videos.current[other.id]; if (!peer || other.id === clip.id) continue;
                  if (isAligned && (other.id === reference?.id || other.sync)) { const target = video.currentTime + (offsets[clip.id] ?? 0) - (offsets[other.id] ?? 0); if (target >= 0 && target <= peer.duration) { peer.currentTime = target; void peer.play().catch(() => {}); } }
                  else peer.pause();
                }
              }} onPause={() => { if (leader.current === clip.id) for (const other of workspace.media) if (other.id !== clip.id && (other.id === reference?.id || other.sync)) videos.current[other.id]?.pause(); }} onTimeUpdate={(event) => {
                if (leader.current !== clip.id) return;
                const t = event.currentTarget.currentTime + (offsets[clip.id] ?? 0); setCommonTime(t);
                for (const other of workspace.media) {
                  if (other.id === clip.id || (other.id !== reference?.id && !other.sync)) continue;
                  const peer = videos.current[other.id]; if (!peer || peer.readyState < 1) continue;
                  const target = t - (offsets[other.id] ?? 0); if (target >= 0 && target <= peer.duration && Math.abs(peer.currentTime - target) > 0.35) peer.currentTime = target;
                }
              }} /> : <div className="review-out-of-coverage">This clip does not cover shared time {commonTime.toFixed(2)} s.</div>}
              <p className="review-source-hash">Original SHA-256 · {clip.sha256.slice(0, 16)}…</p>
              <div className="review-offset-form">
                {index === 0 ? <p className="text-sm">This clip defines time zero. It is not independently synchronized to a camera clock.</p> : <>
                  <label>Offset (seconds)<input type="number" step="0.01" value={offsets[clip.id] ?? 0} onChange={(event) => setOffsets((old) => ({ ...old, [clip.id]: Number(event.target.value) || 0 }))} /></label>
                  <label>Uncertainty ± seconds<input type="number" min="0" max="60" step="0.01" value={uncertainties[clip.id] ?? 0.5} onChange={(event) => setUncertainties((old) => ({ ...old, [clip.id]: Number(event.target.value) || 0 }))} /></label>
                  <div className="review-anchor-row"><button className="btn btn-secondary btn-sm" onClick={() => setAnchorSource((old) => ({ ...old, [clip.id]: videos.current[clip.id]?.currentTime ?? null }))}>Use this clip playhead as event anchor</button><button className="btn btn-secondary btn-sm" onClick={() => setAnchorReference((old) => ({ ...old, [clip.id]: videos.current[reference!.id]?.currentTime ?? null }))}>Use reference playhead as matching anchor</button></div>
                  <p className="text-xs text-tertiary">Matched anchors: clip {anchorSource[clip.id]?.toFixed(2) ?? "not set"} s; reference {anchorReference[clip.id]?.toFixed(2) ?? "not set"} s. Offset = reference time − clip time.</p>
                  <label>How was this alignment estimated?<input value={bases[clip.id] ?? ""} maxLength={300} placeholder="e.g. same vehicle enters frame" onChange={(event) => setBases((old) => ({ ...old, [clip.id]: event.target.value }))} /></label>
                  {clip.sync && <p className="text-xs text-secondary">Saved version {clip.sync.version} · {clip.sync.offset_seconds.toFixed(2)} ± {clip.sync.uncertainty_seconds.toFixed(2)} s · estimate, not verified synchronization</p>}
                </>}
                <button className="btn btn-primary btn-sm" disabled={!!busy[`sync-${clip.id}`] || (index > 0 && !bases[clip.id]?.trim())} onClick={() => void saveOffset(clip, index)}>{busy[`sync-${clip.id}`] ? "Saving…" : index === 0 ? "Set reference timeline" : clip.sync ? "Save new alignment version" : "Save estimated alignment"}</button>
              </div>
            </article>;
          })}
        </div>
        <div className="review-note"><strong>Interpretation:</strong> offsets are manual estimates. The displayed ± value is reviewer-entered uncertainty, not an independently measured error. Unaligned clips remain viewable individually.</div>
      </section>

      <details className="card card-body review-disclosure review-acoustic-section">
        <summary className="review-disclosure-summary"><span className="review-disclosure-index">02</span><span><strong>Review audio cues</strong><small>Optional screening for unusual sound energy in the original clip.</small></span><span className="review-disclosure-action">Open section <span aria-hidden="true">＋</span></span></summary>
        <div className="review-disclosure-body"><h2>Candidate acoustic transients</h2>
        <p className="text-sm text-secondary">Blackbox flags unusually high short-window audio energy. It does not label a transient as a horn, impact, or braking sound. Open the corresponding moment in the source video/audio and add a reviewer annotation if useful.</p>
        <div className="review-audio-grid">{workspace.media.map((clip) => {
          const result = analysis[clip.id];
          const clipOffset = offsets[clip.id] ?? 0;
          return <article className="review-audio-card" key={clip.id}><div className="review-section-title"><h3>{clip.filename}</h3><button className="btn btn-secondary btn-sm" disabled={!clip.has_audio || !!busy[`audio-${clip.id}`]} onClick={() => void analyze(clip)}>{busy[`audio-${clip.id}`] ? "Scanning audio…" : result ? "Re-scan original audio" : clip.has_audio ? "Find transient candidates" : "No audio track"}</button></div>
            {result && <><p className="text-xs text-tertiary">Source SHA-256 {result.source_sha256.slice(0, 16)}… · {result.events.length} candidate(s) · {String(result.method.method)}</p>
              {!result.events.length && <p className="text-sm">No transients passed the screening threshold. This does not establish that the clip contains no relevant sound.</p>}
              <ul className="review-event-list">{result.events.map((event, i) => {
                const global = event.timestamp_seconds + clipOffset;
                const sourceAligned = clip.id === reference?.id || !!clip.sync;
                const nearby = annotations.map((item) => {
                  const sameClip = item.media_id === clip.id;
                  const annotationMedia = workspace.media.find((candidate) => candidate.id === item.media_id);
                  const comparable = sameClip || (sourceAligned && (item.media_id === reference?.id || !!annotationMedia?.sync));
                  const delta = sameClip ? Math.abs(item.timestamp_seconds - event.timestamp_seconds) : Math.abs(item.timestamp_seconds + (offsets[item.media_id] ?? 0) - global);
                  return { item, delta, comparable };
                }).filter((item) => item.comparable && item.delta <= 1.5).sort((a, b) => a.delta - b.delta)[0];
                return <li key={`${event.timestamp_seconds}-${i}`}><button className="review-event-jump" onClick={() => seekAll(global, clip.id, event.timestamp_seconds)}><strong>{event.timestamp_seconds.toFixed(2)} s</strong> · {event.label} · {event.relative_level.toFixed(1)}× local median</button><span>{nearby ? `Closest reviewer annotation: “${nearby.item.label}” · ${nearby.delta.toFixed(2)} s apart${nearby.item.media_id === clip.id ? " (same clip)" : " (estimated cross-clip alignment)"}` : "No comparable reviewer visual annotation within 1.5 s"}</span></li>;
              })}</ul><p className="review-note">{result.limitation}</p></>}
          </article>;
        })}</div>
        </div>
      </details>

      <details className="card card-body review-disclosure review-annotation-section">
        <summary className="review-disclosure-summary"><span className="review-disclosure-index">03</span><span><strong>Add a frame note</strong><small>Save an observation linked to a specific source moment.</small></span><span className="review-disclosure-action">Open section <span aria-hidden="true">＋</span></span></summary>
        <div className="review-disclosure-body"><h2>Record what a reviewer sees</h2>
        <p className="text-sm text-secondary">Freeze a source frame, mark an optional image point, and save a source-linked note. Corrections append a new version; previous versions remain available for review and export. The source presentation timestamp is the primary locator; frame numbers use nominal FPS and are approximate for variable-frame-rate clips.</p>
        <div className="review-annotation-grid">
          <div className="review-annotation-editor">
            <label>Source clip<select value={annotationMediaId} onChange={(event) => { setAnnotationMediaId(event.target.value); setFrozenFrame(""); setImagePoint(null); setAnnotationKey(""); }}>
              {workspace.media.map((clip) => <option key={clip.id} value={clip.id}>{clip.filename}</option>)}
            </select></label>
            <div className="review-annotation-video">{workspace.media.filter((clip) => clip.id === annotationMediaId).map((clip) => <video key={clip.id} ref={annotationVideo} crossOrigin="use-credentials" src={mediaApi.streamUrl(caseId, clip.id)} controls preload="metadata" onLoadedMetadata={(event) => { if (pendingFrameSeek != null) { event.currentTarget.currentTime = pendingFrameSeek; setPendingFrameSeek(null); } }} onTimeUpdate={(event) => setFrameTime(event.currentTarget.currentTime)} />)}</div>
            <div className="review-annotation-actions"><button className="btn btn-secondary" onClick={freezeFrame}>Pause and freeze current frame</button><span>{frameTime.toFixed(3)} s · frame {frameIndex}</span></div>
            {frozenFrame && <div className="review-still-wrap"><p className="text-xs">Still image from the original clip. Click to place an optional point.</p><div className="review-still" onClick={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              const clip = workspace.media.find((item) => item.id === annotationMediaId);
              const naturalW = clip?.width ?? rect.width, naturalH = clip?.height ?? rect.height;
              const scale = Math.min(rect.width / naturalW, rect.height / naturalH);
              const shownW = naturalW * scale, shownH = naturalH * scale;
              const left = rect.left + (rect.width - shownW) / 2, top = rect.top + (rect.height - shownH) / 2;
              const x = (event.clientX - left) / shownW, y = (event.clientY - top) / shownH;
              if (x >= 0 && x <= 1 && y >= 0 && y <= 1) setImagePoint({ x, y });
            }}><Image src={frozenFrame} alt="Frozen source frame for annotation" width={workspace.media.find((item) => item.id === annotationMediaId)?.width ?? 1280} height={workspace.media.find((item) => item.id === annotationMediaId)?.height ?? 720} unoptimized />{imagePoint && <span className="review-mark" style={{ left: `${imagePoint.x * 100}%`, top: `${imagePoint.y * 100}%` }}>＋</span>}</div>
              {imagePoint && <p className="text-xs">Marked image point: x {imagePoint.x.toFixed(3)}, y {imagePoint.y.toFixed(3)} of source frame</p>}</div>}
            <div className="review-annotation-fields"><label>What are you marking?<select value={annotationKind} onChange={(event) => setAnnotationKind(event.target.value as typeof annotationKind)}><option value="event">Event</option><option value="signal_state">Signal state</option><option value="stop_line">Stop line</option><option value="ground_contact">Ground-contact point</option><option value="occlusion_boundary">Occlusion boundary</option><option value="road_condition">Visible road condition</option><option value="note">Reviewer note</option></select></label>
              <label>Short label<input value={annotationLabel} maxLength={120} placeholder="e.g. vehicle first enters junction" onChange={(event) => setAnnotationLabel(event.target.value)} /></label>
              <label>Reviewer note<textarea rows={3} value={annotationNote} maxLength={2000} placeholder="Describe only what is visible; separate interpretation from observation." onChange={(event) => setAnnotationNote(event.target.value)} /></label>
              <button className="btn btn-primary" disabled={!frozenFrame || !annotationLabel.trim() || !!busy.annotation} onClick={() => void saveAnnotation()}>{busy.annotation ? "Saving version…" : annotationKey ? "Save correction as a new version" : "Save source-linked annotation"}</button>
              {annotationKey && <button className="btn btn-ghost" onClick={() => { setAnnotationKey(""); setAnnotationLabel(""); setAnnotationNote(""); setImagePoint(null); }}>Start a separate annotation</button>}
            </div>
          </div>
          <aside className="review-history"><h3>Annotation history</h3>{!annotations.length && <p className="text-sm text-tertiary">No reviewer annotations yet.</p>}
            {[...versions.entries()].map(([key, unsorted]) => { const rows = [...unsorted].sort((a, b) => a.version - b.version); return <article className="review-history-item" key={key}><p className="text-xs text-tertiary">{rows.length} version{rows.length !== 1 ? "s" : ""} · {rows[0].kind.replaceAll("_", " ")}</p>{rows.map((item) => <div className="review-version" key={item.version_id}><div><strong>v{item.version} · {item.label}</strong><span>{workspace.media.find((clip) => clip.id === item.media_id)?.filename} · {item.timestamp_seconds.toFixed(3)} s · frame {item.frame_index}</span>{item.x_normalized != null && <span>Image point ({item.x_normalized.toFixed(3)}, {item.y_normalized?.toFixed(3)})</span>}{item.note && <p>{item.note}</p>}<span>{item.frame_index_basis}</span><span>Source SHA-256 {item.source_sha256.slice(0, 14)}… · {new Date(item.created_at).toLocaleString()}</span></div><button className="btn btn-ghost btn-sm" onClick={() => beginCorrection(item)}>Correct</button></div>)}</article>; })}
          </aside>
        </div>
        <p className="review-note">Annotations are reviewer observations, not system findings. The source video remains unchanged; each saved version records its source hash, clip time, frame index, actor, and predecessor.</p>
        </div>
      </details>
    </>}
  </main>;
}

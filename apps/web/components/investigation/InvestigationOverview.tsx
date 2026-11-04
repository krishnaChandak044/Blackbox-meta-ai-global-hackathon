"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  claimsApi, phase5Api, reviewWorkspaceApi, tracksApi,
  type ClaimVerdict, type EvidenceNeed, type FrameAnnotation,
  type Job, type SourceMedia, type TrackSummary, type TranscriptClaim,
} from "@/lib/api";

type ClipTracks = { media: SourceMedia; tracks: TrackSummary[]; error?: string };

export default function InvestigationOverview({ caseId, media, jobs }: { caseId: string; media: SourceMedia[]; jobs: Job[] }) {
  const [clipTracks, setClipTracks] = useState<ClipTracks[]>([]);
  const [annotations, setAnnotations] = useState<FrameAnnotation[]>([]);
  const [needs, setNeeds] = useState<EvidenceNeed[]>([]);
  const [claims, setClaims] = useState<{ claim: TranscriptClaim; verdict: ClaimVerdict | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const completedJobs = jobs.filter(job => job.status === "done").map(job => job.id).join(",");

  useEffect(() => {
    if (!media.length) { setLoading(false); return; }
    let cancelled = false;
    async function load() {
      const [trackResults, workspace, evidence, claimList] = await Promise.all([
        Promise.all(media.map(async clip => {
          try { return { media: clip, tracks: await tracksApi.list(caseId, clip.id) }; }
          catch (cause) { return { media: clip, tracks: [], error: cause instanceof Error ? cause.message : "Tracks unavailable" }; }
        })),
        reviewWorkspaceApi.get(caseId).catch(() => null),
        phase5Api.evidenceNeeds(caseId).catch(() => null),
        claimsApi.list(caseId).catch(() => [] as TranscriptClaim[]),
      ]);
      const checkedClaims = await Promise.all(claimList.map(async claim => ({
        claim,
        verdict: await claimsApi.getCheck(caseId, claim.id).catch(() => null),
      })));
      if (cancelled) return;
      setClipTracks(trackResults);
      setAnnotations(workspace?.annotations ?? []);
      setNeeds(evidence?.needs ?? []);
      setClaims(checkedClaims);
      setError(null);
      setLoading(false);
    }
    void load().catch(cause => {
      if (!cancelled) { setError(cause instanceof Error ? cause.message : "Could not load the investigation"); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, [caseId, media, completedJobs]);

  if (!media.length) return null;
  const active = jobs.some(job => job.status === "queued" || job.status === "running" || job.status === "retrying");
  const visibleTracks = clipTracks.flatMap(clip => clip.tracks);
  const reviewedTracks = visibleTracks.filter(track => track.is_human_confirmed);
  const firstNeed = needs.find(need => need.state !== "resolved" && need.state !== "dismissed");

  return <section className="card mb-6" aria-label="Investigation overview">
    <div className="card-body" style={{ display: "grid", gap: 20 }}>
      <div><p className="eyebrow">Investigation</p><h2 style={{ fontSize: "var(--text-xl)", marginTop: 4 }}>What the footage can tell us</h2>
        <p className="text-sm text-secondary mt-2">Results update as each clip finishes processing. Every observation links back to the source. Physical measurements appear only after validated calibration.</p></div>
      {loading ? <p className="text-sm text-secondary" role="status">Loading evidence…</p> : error ? <p className="alert alert-error" role="alert">{error}</p> : <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 12 }}>
          <div className="card card-body"><strong>Original footage</strong><p className="text-sm text-secondary mt-1">{media.filter(clip => clip.status === "indexed").length} of {media.length} clips indexed{active ? " · analysis in progress" : ""}</p></div>
          <div className="card card-body"><strong>Detected objects</strong><p className="text-sm text-secondary mt-1">{visibleTracks.length} tracks found · {reviewedTracks.length} confirmed by a reviewer</p></div>
          <div className="card card-body"><strong>Frame-linked notes</strong><p className="text-sm text-secondary mt-1">{annotations.length} reviewed observations</p></div>
        </div>
        <div><h3 style={{ fontSize: 17 }}>Visible in the clips</h3>
          {clipTracks.map(clip => <div key={clip.media.id} className="text-sm" style={{ padding: "10px 0", borderBottom: "1px solid var(--border-color, #e5e7eb)" }}>
            <Link href={`/cases/${caseId}/media/${clip.media.id}/tracks`}>{clip.media.original_filename}</Link>
            <span className="text-secondary"> · {clip.error ? "Tracks unavailable" : clip.tracks.length ? `${clip.tracks.length} detected track${clip.tracks.length === 1 ? "" : "s"}; review their labels before relying on them` : active ? "Analyzing…" : "No objects confirmed yet"}</span>
          </div>)}
          {annotations.slice(0, 5).map(note => <div key={note.version_id} className="text-sm" style={{ padding: "8px 0" }}><Link href={`/cases/${caseId}/review-workspace`}>{note.label} · {note.timestamp_seconds.toFixed(1)} s</Link><span className="text-secondary"> · reviewer note, source frame {note.frame_index}</span></div>)}
        </div>
        <div><h3 style={{ fontSize: 17 }}>Claims and uncertainty</h3>
          {claims.length ? claims.slice(0, 4).map(({ claim, verdict }) => <p className="text-sm" key={claim.id} style={{ marginTop: 8 }}><Link href={`/cases/${caseId}/claims`}>{claim.raw_text}</Link><span className="text-secondary"> · {verdict ? `${verdict.verdict}: ${verdict.explanation}` : "Not checked against footage"}</span></p>) : <p className="text-sm text-secondary mt-1">No testimony claims added. Source footage can still be reviewed and exported.</p>}
          <p className="text-sm text-secondary mt-2">Speed, distance, braking, and a physical 3D path require a validated scale. An uncalibrated clip cannot establish them.</p>
        </div>
        {firstNeed && <div className="alert alert-info"><strong>Most useful next evidence:</strong> {firstNeed.title}. <Link href={`/cases/${caseId}/reports`}>See why it helps →</Link></div>}
        <div className="flex gap-2" style={{ flexWrap: "wrap" }}><Link className="btn btn-primary" href={`/cases/${caseId}/review-workspace`}>Review clips and frames</Link><Link className="btn btn-secondary" href={`/cases/${caseId}/reports`}>Create evidence package</Link></div>
      </>}
    </div>
  </section>;
}

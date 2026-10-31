"use client";

/**
 * /cases/[id]/media/[mediaId]/tracks
 *
 * Trajectory viewer — video player synced with SVG bounding-box overlay.
 * – Runs tracking job.
 * – Lists all tracks with category badge and confidence.
 * – Clicking a track row highlights it in the overlay.
 * – Confirm / delete tracks.
 * – Shows world position + 1σ uncertainty for calibrated clips.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import VideoPlayer from "@/components/player/VideoPlayer";
import TrajectoryOverlay from "@/components/player/TrajectoryOverlay";
import { jobsApi, mediaApi, tracksApi } from "@/lib/api";
import type { SourceMedia, TrackDetail, TrackSummary } from "@/lib/api";

interface PageProps {
  params: { id: string; mediaId: string };
}

const CATEGORY_COLOR: Record<string, string> = {
  vehicle:    "#7BAE7F",
  pedestrian: "#6BA3BF",
  cyclist:    "#C9A96E",
  unknown:    "#9B8EC4",
};

export default function TracksPage({ params }: PageProps) {
  const { id: caseId, mediaId } = params;

  const [media,    setMedia]    = useState<SourceMedia | null>(null);
  const [summaries, setSummaries] = useState<TrackSummary[]>([]);
  const [details,  setDetails]  = useState<Map<string, TrackDetail>>(new Map());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [currentFrame, setCurrentFrame] = useState(0);
  const [loading, setLoading]   = useState(true);
  const [running, setRunning]   = useState(false);
  const [error,   setError]     = useState<string | null>(null);

  const fps = media?.fps_nominal ?? 30;
  const videoW = media?.width  ?? 1920;
  const videoH = media?.height ?? 1080;

  // ── Load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    try {
      const [m, ts] = await Promise.all([
        mediaApi.get(caseId, mediaId),
        tracksApi.list(caseId, mediaId),
      ]);
      setMedia(m);
      setSummaries(ts);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, [caseId, mediaId]);

  useEffect(() => { load(); }, [load]);

  // ── Load full track detail lazily ─────────────────────────────────────────
  const loadDetail = async (trackId: string) => {
    if (details.has(trackId)) return;
    try {
      const d = await tracksApi.get(caseId, mediaId, trackId);
      setDetails(prev => new Map(prev).set(trackId, d));
    } catch (e: any) { setError(e.message); }
  };

  const toggleSelect = async (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) { next.delete(id); } else { next.add(id); await loadDetail(id); }
    setSelected(next);
  };

  // ── Run tracking ──────────────────────────────────────────────────────────
  const runTracking = async () => {
    setRunning(true); setError(null);
    try {
      const queued = await tracksApi.run(caseId, mediaId);
      for (let attempt = 0; attempt < 60; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const job = await jobsApi.get(queued.job_id);
        if (job.status === "failed") throw new Error(job.error_message ?? "Tracking failed");
        if (job.status === "done") {
          setSummaries(await tracksApi.list(caseId, mediaId));
          setDetails(new Map());
          setSelected(new Set());
          setRunning(false);
          return;
        }
      }
      throw new Error("Tracking is still running. Refresh this page to see its result.");
    } catch (e: any) { setError(e.message); setRunning(false); }
  };

  // ── Confirm / delete ──────────────────────────────────────────────────────
  const confirmTrack = async (id: string) => {
    await tracksApi.confirm(caseId, mediaId, id);
    setSummaries(prev => prev.map(t => t.id === id ? { ...t, is_human_confirmed: true } : t));
  };

  const deleteTrack = async (id: string) => {
    await tracksApi.delete(caseId, mediaId, id);
    setSummaries(prev => prev.filter(t => t.id !== id));
    const next = new Set(selected); next.delete(id);
    setSelected(next);
  };

  // Collect detailed tracks for overlay
  const overlayTracks = Array.from(selected)
    .map(id => details.get(id))
    .filter(Boolean) as TrackDetail[];

  if (loading) return <div className="p-8 text-tertiary">Loading…</div>;

  // Video URL — served from the original storage endpoint
  const videoSrc = mediaApi.streamUrl(caseId, mediaId);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "var(--space-5)", padding: "var(--space-5)", height: "calc(100vh - 64px)", overflow: "hidden" }}>

      {/* ── Left: video + overlay ───────────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", minHeight: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Link href={`/cases/${caseId}`} className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 13 }}>← Back</Link>
          <div>
            <h1 className="heading-sm" style={{ margin: 0 }}>Object Trajectories</h1>
            <p className="text-sm text-tertiary" style={{ margin: 0 }}>{media?.original_filename}</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: "var(--space-2)" }}>
            <Link
              href={`/cases/${caseId}/media/${mediaId}/calibration`}
              className="btn btn-ghost"
              style={{ fontSize: 13 }}
            >
              ⊞ Calibration
            </Link>
            <button
              className="btn btn-primary"
              onClick={runTracking}
              disabled={running}
              style={{ fontSize: 13 }}
            >
              {running ? "Tracking…" : summaries.length > 0 ? "Re-run tracking" : "Run tracking"}
            </button>
          </div>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        {/* Video player with overlay */}
        <div style={{ flex: 1, minHeight: 0 }}>
          <VideoPlayer
            src={videoSrc}
            fps={fps}
            onFrameChange={setCurrentFrame}
            height={500}
            overlay={
              overlayTracks.length > 0 ? (
                <TrajectoryOverlay
                  tracks={overlayTracks}
                  currentFrame={currentFrame}
                  videoWidth={videoW}
                  videoHeight={videoH}
                />
              ) : undefined
            }
          />
        </div>

        {/* Current frame info */}
        {overlayTracks.length > 0 && (
          <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
            {overlayTracks.map(track => {
              const pt = track.points.find(p => p.frame_index === currentFrame);
              if (!pt) return null;
              return (
                <div key={track.id} className="card" style={{
                  padding: "var(--space-2) var(--space-3)", fontSize: 12,
                  borderLeft: `3px solid ${CATEGORY_COLOR[track.category] ?? "var(--text-tertiary)"}`,
                }}>
                  <strong>{track.category}</strong>
                  <span className="text-tertiary" style={{ marginLeft: 8 }}>
                    f{pt.frame_index} · {pt.presentation_ts_s.toFixed(3)}s
                  </span>
                  {pt.world_x != null && (
                    <span style={{ marginLeft: 8, fontFamily: "var(--font-mono)" }}>
                      ({pt.world_x.toFixed(2)}, {pt.world_y?.toFixed(2)}) m
                      {pt.sigma_m != null && ` ±${pt.sigma_m.toFixed(2)}`}
                    </span>
                  )}
                  {pt.world_x == null && (
                    <span className="text-tertiary" style={{ marginLeft: 8, fontStyle: "italic" }}>
                      no calibration
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Right: track list ───────────────────────────────────────────── */}
      <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <p className="heading-xs" style={{ margin: 0, padding: "var(--space-1) 0" }}>
          Detected tracks ({summaries.length})
        </p>

        {summaries.length === 0 && !running && (
          <div className="card" style={{ padding: "var(--space-5)", textAlign: "center" }}>
            <p className="text-sm text-tertiary">No tracks yet.</p>
            <p className="text-sm text-tertiary">Click <strong>Run tracking</strong> to detect objects.</p>
          </div>
        )}

        {running && (
          <div className="card" style={{ padding: "var(--space-4)", textAlign: "center" }}>
            <div style={{ fontSize: 24, marginBottom: 8 }}>⏳</div>
            <p className="text-sm text-tertiary">Tracking in progress…</p>
          </div>
        )}

        {summaries.map(track => {
          const isSelected = selected.has(track.id);
          const color = CATEGORY_COLOR[track.category] ?? "var(--text-tertiary)";
          return (
            <div
              key={track.id}
              className="card"
              onClick={() => toggleSelect(track.id)}
              style={{
                padding: "var(--space-3) var(--space-4)",
                cursor: "pointer",
                borderLeft: `3px solid ${isSelected ? color : "transparent"}`,
                background: isSelected ? "var(--bg-secondary)" : undefined,
                transition: "all var(--duration-sm)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: 4 }}>
                <span style={{
                  background: color, color: "#fff", fontSize: 11, fontWeight: 600,
                  padding: "2px 8px", borderRadius: "var(--radius-pill)",
                }}>
                  {track.category}
                </span>
                {track.is_human_confirmed && (
                  <span style={{ fontSize: 11, color: "var(--sage-mid)", fontWeight: 600 }}>✓ confirmed</span>
                )}
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                  f{track.first_frame}–{track.last_frame}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                {track.point_count} pts · {track.tracker_model}
              </div>

              {/* Actions (visible on hover / selection) */}
              {isSelected && (
                <div
                  style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}
                  onClick={e => e.stopPropagation()}
                >
                  {!track.is_human_confirmed && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 11, padding: "2px 10px" }}
                      onClick={() => confirmTrack(track.id)}
                    >
                      ✓ Confirm
                    </button>
                  )}
                  <button
                    className="btn btn-ghost"
                    style={{ fontSize: 11, padding: "2px 10px", color: "var(--rose-mid)" }}
                    onClick={() => deleteTrack(track.id)}
                  >
                    ✕ Delete
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

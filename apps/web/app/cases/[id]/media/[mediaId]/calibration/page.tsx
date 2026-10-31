"use client";

/**
 * /cases/[id]/media/[mediaId]/calibration
 *
 * Ground-plane calibration anchor editor.
 * – Click the video frame to place an anchor.
 * – Enter label + real-world (x, y) in metres.
 * – Optionally mark a distance-reference pair.
 * – Fit the homography and see per-anchor reprojection errors.
 * – A RMSE > 2 px is highlighted in amber; > 5 px in rose.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { calibrationApi, mediaApi } from "@/lib/api";
import type { CalibrationAnchor, HomographyFit, SourceMedia } from "@/lib/api";

interface PageProps {
  params: { id: string; mediaId: string };
}

const RMSE_WARN  = 2.0;
const RMSE_ERROR = 5.0;

export default function CalibrationPage({ params }: PageProps) {
  const { id: caseId, mediaId } = params;

  const [media,   setMedia]   = useState<SourceMedia | null>(null);
  const [anchors, setAnchors] = useState<CalibrationAnchor[]>([]);
  const [fit,     setFit]     = useState<HomographyFit | null>(null);
  const [loading, setLoading] = useState(true);
  const [fitting, setFitting] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  // Pending anchor being placed
  const [pending, setPending] = useState<{
    pixel_x: number; pixel_y: number;
    label: string; world_x: string; world_y: string;
    known_distance_m: string; is_distance_ref_b: boolean;
  } | null>(null);

  const imgRef = useRef<HTMLVideoElement>(null);

  // ── Load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    try {
      const [m, a, f] = await Promise.all([
        mediaApi.get(caseId, mediaId),
        calibrationApi.listAnchors(caseId, mediaId),
        calibrationApi.getActiveFit(caseId, mediaId).catch(() => null),
      ]);
      setMedia(m);
      setAnchors(a);
      setFit(f);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [caseId, mediaId]);

  useEffect(() => { load(); }, [load]);

  // ── Click on frame to place anchor ────────────────────────────────────────
  const handleFrameClick = (e: React.MouseEvent<HTMLVideoElement>) => {
    if (!media?.width || !media?.height) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = (media.width) / rect.width;
    const scaleY = (media.height) / rect.height;
    const px = (e.clientX - rect.left) * scaleX;
    const py = (e.clientY - rect.top)  * scaleY;
    setPending({ pixel_x: px, pixel_y: py, label: "", world_x: "", world_y: "", known_distance_m: "", is_distance_ref_b: false });
  };

  const confirmAnchor = async () => {
    if (!pending || !pending.label || pending.world_x === "" || pending.world_y === "") return;
    try {
      const a = await calibrationApi.addAnchor(caseId, mediaId, {
        label: pending.label,
        pixel_x: pending.pixel_x,
        pixel_y: pending.pixel_y,
        world_x: parseFloat(pending.world_x),
        world_y: parseFloat(pending.world_y),
        known_distance_m: pending.known_distance_m ? parseFloat(pending.known_distance_m) : undefined,
        is_distance_ref_b: pending.is_distance_ref_b,
      });
      setAnchors(prev => [...prev, a]);
      setPending(null);
    } catch (e: any) { setError(e.message); }
  };

  const deleteAnchor = async (id: string) => {
    await calibrationApi.deleteAnchor(caseId, mediaId, id);
    setAnchors(prev => prev.filter(a => a.id !== id));
    setFit(null);
  };

  const fitHomography = async () => {
    setFitting(true);
    setError(null);
    try {
      const f = await calibrationApi.fitHomography(caseId, mediaId);
      setFit(f);
      // Refresh anchors to get updated per-anchor errors
      const a = await calibrationApi.listAnchors(caseId, mediaId);
      setAnchors(a);
    } catch (e: any) { setError(e.message); }
    finally { setFitting(false); }
  };

  // ── RMSE colour ───────────────────────────────────────────────────────────
  const rmseColor = (rmse: number) =>
    rmse > RMSE_ERROR ? "var(--rose-mid)" : rmse > RMSE_WARN ? "var(--sand-mid)" : "var(--sage-mid)";

  const errColor = (e: number | null) =>
    !e ? "var(--text-tertiary)" : e > RMSE_ERROR ? "var(--rose-mid)" : e > RMSE_WARN ? "var(--sand-mid)" : "var(--sage-mid)";

  // ── Render ────────────────────────────────────────────────────────────────
  if (loading) return <div className="p-8 text-tertiary">Loading…</div>;

  const frameUrl = media ? mediaApi.streamUrl(caseId, mediaId) : null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: "var(--space-5)", padding: "var(--space-5)", height: "calc(100vh - 64px)", overflow: "hidden" }}>

      {/* ── Left: frame + overlay ───────────────────────────────────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Link href={`/cases/${caseId}`} className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 13 }}>← Back</Link>
          <div>
            <h1 className="heading-sm" style={{ margin: 0 }}>Ground-Plane Calibration</h1>
            <p className="text-sm text-tertiary" style={{ margin: 0 }}>{media?.original_filename}</p>
          </div>
        </div>

        {/* Frame click area */}
        <div style={{ position: "relative", width: "100%", background: "#111" }}>
          {frameUrl && <video
            ref={imgRef}
            src={frameUrl}
            crossOrigin="use-credentials"
            preload="metadata"
            controls
            onClick={handleFrameClick}
            style={{ width: "100%", display: "block", cursor: "crosshair" }}
            title="Pause on a frame, then click a ground-plane point"
          />}

          {/* Anchor dots overlay */}
          <svg
            viewBox={`0 0 ${media?.width ?? 1920} ${media?.height ?? 1080}`}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
          >
            {anchors.map((a, i) => {
              const err = a.reprojection_error_px;
              const color = errColor(err);
              return (
                <g key={a.id}>
                  <circle cx={a.pixel_x} cy={a.pixel_y} r={8} fill={color} fillOpacity={0.7} stroke="white" strokeWidth={1.5} />
                  <text x={a.pixel_x + 10} y={a.pixel_y + 4} fontSize={11} fill="white" fontFamily="Inter,sans-serif"
                    style={{ textShadow: "0 1px 3px rgba(0,0,0,0.8)" }}>
                    {i + 1}. {a.label}
                    {err != null ? ` (${err.toFixed(1)}px)` : ""}
                  </text>
                </g>
              );
            })}

            {/* Pending anchor */}
            {pending && (
              <circle cx={pending.pixel_x} cy={pending.pixel_y} r={8}
                fill="var(--sky-mid)" fillOpacity={0.6}
                stroke="white" strokeWidth={2} strokeDasharray="4 3" />
            )}
          </svg>
        </div>

        {/* Pending anchor form */}
        {pending && (
          <div className="card" style={{ padding: "var(--space-4)", background: "var(--sky-light)" }}>
            <p className="text-sm" style={{ marginBottom: "var(--space-3)", fontWeight: 600 }}>
              New anchor at ({pending.pixel_x.toFixed(0)}, {pending.pixel_y.toFixed(0)})
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-3)" }}>
              <div className="form-group" style={{ gridColumn: "1/-1" }}>
                <label className="form-label">Label</label>
                <input className="form-input" placeholder="e.g. stop-line NW corner"
                  value={pending.label} onChange={e => setPending(p => p && ({ ...p, label: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">World X (m east)</label>
                <input className="form-input" type="number" placeholder="0.0"
                  value={pending.world_x} onChange={e => setPending(p => p && ({ ...p, world_x: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">World Y (m north)</label>
                <input className="form-input" type="number" placeholder="0.0"
                  value={pending.world_y} onChange={e => setPending(p => p && ({ ...p, world_y: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Ref. distance (m) <span className="text-tertiary" style={{ fontWeight: 400 }}>optional</span></label>
                <input className="form-input" type="number" placeholder="—"
                  value={pending.known_distance_m} onChange={e => setPending(p => p && ({ ...p, known_distance_m: e.target.value }))} />
              </div>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginTop: "var(--space-2)", fontSize: 13 }}>
              <input type="checkbox" checked={pending.is_distance_ref_b}
                onChange={e => setPending(p => p && ({ ...p, is_distance_ref_b: e.target.checked }))} />
              This is the second anchor of the distance reference pair
            </label>
            <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
              <button className="btn btn-primary" onClick={confirmAnchor}>Add anchor</button>
              <button className="btn btn-ghost" onClick={() => setPending(null)}>Cancel</button>
            </div>
          </div>
        )}
      </div>

      {/* ── Right: sidebar ──────────────────────────────────────────────── */}
      <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>

        {/* Fit result */}
        {fit && (
          <div className="card" style={{ padding: "var(--space-4)", borderLeft: `3px solid ${rmseColor(fit.reprojection_rmse_px)}` }}>
            <p className="heading-xs" style={{ margin: "0 0 var(--space-2)" }}>Active Homography</p>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <tbody>
                <tr><td className="text-tertiary">RMSE</td>
                  <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: rmseColor(fit.reprojection_rmse_px) }}>
                    {fit.reprojection_rmse_px.toFixed(2)} px
                  </td></tr>
                <tr><td className="text-tertiary">Condition №</td>
                  <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>{fit.condition_number.toFixed(0)}</td></tr>
                <tr><td className="text-tertiary">Anchors</td>
                  <td style={{ textAlign: "right" }}>{fit.anchor_count}</td></tr>
                {fit.scale_metres_per_pixel != null && (
                  <tr><td className="text-tertiary">Scale</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--sage-mid)" }}>
                      {fit.scale_metres_per_pixel.toFixed(4)} m/px
                    </td></tr>
                )}
                {fit.scale_metres_per_pixel == null && (
                  <tr><td colSpan={2} style={{ color: "var(--rose-mid)", fontSize: 12, paddingTop: 6 }}>
                    ⚠ No distance reference — absolute speed unavailable
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Fit button */}
        <button
          className="btn btn-primary"
          onClick={fitHomography}
          disabled={fitting || anchors.length < 4}
          style={{ width: "100%" }}
        >
          {fitting ? "Fitting…" : anchors.length < 4
            ? `Fit homography (need ${4 - anchors.length} more anchor${anchors.length === 3 ? "" : "s"})`
            : "Fit / refit homography"}
        </button>

        {error && <div className="alert alert-error">{error}</div>}

        {/* Anchors table */}
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="heading-xs" style={{ margin: 0 }}>Anchors ({anchors.length})</span>
          </div>
          {anchors.length === 0 ? (
            <p className="text-sm text-tertiary" style={{ padding: "var(--space-4)", margin: 0 }}>
              Click on the frame to place anchors. You need at least 4 non-collinear points.
            </p>
          ) : (
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "var(--bg-secondary)" }}>
                  <th style={{ padding: "6px 12px", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)" }}>#</th>
                  <th style={{ padding: "6px 12px", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)" }}>Label</th>
                  <th style={{ padding: "6px 12px", textAlign: "right", fontWeight: 600, color: "var(--text-secondary)" }}>Error</th>
                  <th style={{ padding: "6px 8px" }}></th>
                </tr>
              </thead>
              <tbody>
                {anchors.map((a, i) => (
                  <tr key={a.id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "6px 12px", color: "var(--text-tertiary)" }}>{i + 1}</td>
                    <td style={{ padding: "6px 12px" }}>
                      <div style={{ fontWeight: 500 }}>{a.label}</div>
                      <div style={{ color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                        px ({a.pixel_x.toFixed(0)}, {a.pixel_y.toFixed(0)}) · w ({a.world_x.toFixed(1)}, {a.world_y.toFixed(1)})
                      </div>
                    </td>
                    <td style={{ padding: "6px 12px", textAlign: "right", fontFamily: "var(--font-mono)", color: errColor(a.reprojection_error_px) }}>
                      {a.reprojection_error_px != null ? `${a.reprojection_error_px.toFixed(1)} px` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <button
                        onClick={() => deleteAnchor(a.id)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-tertiary)", fontSize: 14, lineHeight: 1 }}
                        aria-label="Remove anchor"
                      >✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Instructions */}
        <div className="card" style={{ padding: "var(--space-4)", fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          <p style={{ margin: "0 0 8px", fontWeight: 600 }}>How to calibrate</p>
          <ol style={{ margin: 0, paddingLeft: 16 }}>
            <li>Click on the video frame to place an anchor point.</li>
            <li>Enter the real-world coordinates in metres.</li>
            <li>Place at least 4 non-collinear points.</li>
            <li>For absolute speed: mark two anchors with a known distance.</li>
            <li>Click <strong>Fit homography</strong> and verify RMSE {"<"} 2 px.</li>
            <li>Refit after adding/removing anchors.</li>
          </ol>
        </div>
      </div>
    </div>
  );
}

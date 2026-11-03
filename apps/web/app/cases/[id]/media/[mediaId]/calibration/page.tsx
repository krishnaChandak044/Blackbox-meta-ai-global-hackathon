"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { calibrationApi, mediaApi } from "@/lib/api";
import type { CalibrationAnchor, HomographyFit, SourceMedia } from "@/lib/api";

interface PageProps { params: { id: string; mediaId: string } }
type PendingAnchor = {
  pixel_x: number; pixel_y: number; label: string; world_x: string; world_y: string;
  known_distance_m: string; is_distance_ref_b: boolean;
};

const inputStyle: React.CSSProperties = { width: "100%", padding: "10px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg-primary)", color: "var(--text-primary)" };

export default function CalibrationPage({ params }: PageProps) {
  const { id: caseId, mediaId } = params;
  const [media, setMedia] = useState<SourceMedia | null>(null);
  const [anchors, setAnchors] = useState<CalibrationAnchor[]>([]);
  const [fit, setFit] = useState<HomographyFit | null>(null);
  const [loading, setLoading] = useState(true);
  const [fitting, setFitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAnchor | null>(null);
  const [cameraConfirmed, setCameraConfirmed] = useState(false);
  const [frozenFrame, setFrozenFrame] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const load = useCallback(async () => {
    try {
      const [m, a, f] = await Promise.all([
        mediaApi.get(caseId, mediaId), calibrationApi.listAnchors(caseId, mediaId),
        calibrationApi.getActiveFit(caseId, mediaId).catch(() => null),
      ]);
      setMedia(m); setAnchors(a); setFit(f);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not load calibration data."); }
    finally { setLoading(false); }
  }, [caseId, mediaId]);
  useEffect(() => { void load(); }, [load]);

  const freezeFrame = () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError("The video is still loading. Wait a moment, then freeze the frame again.");
      return;
    }
    video.pause();
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) { setError("Your browser could not capture this frame. Try reloading the page."); return; }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    try {
      setFrozenFrame(canvas.toDataURL("image/jpeg", 0.92));
      setError(null);
      setNotice("Frame frozen. Click points on this still image; the video cannot start while you mark them.");
    } catch {
      setError("Could not freeze this frame. Reload the page and try again.");
    }
  };

  const handleFrameClick = (e: React.MouseEvent<HTMLImageElement>) => {
    const image = e.currentTarget;
    const width = image.naturalWidth || media?.width || 0;
    const height = image.naturalHeight || media?.height || 0;
    const rect = image.getBoundingClientRect();
    if (!width || !height || !rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(width, (e.clientX - rect.left) * width / rect.width));
    const y = Math.max(0, Math.min(height, (e.clientY - rect.top) * height / rect.height));
    setError(null); setNotice(null);
    setPending({ pixel_x: x, pixel_y: y, label: `Point ${anchors.length + 1}`, world_x: "", world_y: "", known_distance_m: "", is_distance_ref_b: false });
  };

  const confirmAnchor = async () => {
    if (!pending) return;
    const wx = Number(pending.world_x), wy = Number(pending.world_y);
    if (!pending.label.trim() || pending.world_x === "" || pending.world_y === "" || !Number.isFinite(wx) || !Number.isFinite(wy)) {
      setError("Enter a point name and both real-world coordinates."); return;
    }
    if (pending.known_distance_m && (!Number.isFinite(Number(pending.known_distance_m)) || Number(pending.known_distance_m) <= 0)) {
      setError("Known distance must be a number greater than zero."); return;
    }
    setSaving(true); setError(null);
    try {
      const a = await calibrationApi.addAnchor(caseId, mediaId, {
        label: pending.label.trim(), pixel_x: pending.pixel_x, pixel_y: pending.pixel_y,
        world_x: wx, world_y: wy,
        known_distance_m: pending.known_distance_m ? Number(pending.known_distance_m) : undefined,
        is_distance_ref_b: pending.is_distance_ref_b,
      });
      setAnchors(prev => [...prev, a]); setFit(null); setPending(null);
      setNotice(`Saved ${a.label}. Add ${Math.max(0, 5 - anchors.length - 1)} more measured point${5 - anchors.length - 1 === 1 ? "" : "s"}; the fifth point independently checks the fit.`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not save this point."); }
    finally { setSaving(false); }
  };

  const deleteAnchor = async (anchorId: string) => {
    setError(null);
    try { await calibrationApi.deleteAnchor(caseId, mediaId, anchorId); setAnchors(prev => prev.filter(a => a.id !== anchorId)); setFit(null); setNotice("Point removed. Fit again after you have at least five measured points."); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not remove this point."); }
  };

  const fitHomography = async () => {
    setFitting(true); setError(null); setNotice(null);
    try {
      const result = await calibrationApi.fitHomography(caseId, mediaId);
      setFit(result); setAnchors(await calibrationApi.listAnchors(caseId, mediaId));
      setNotice(result.scale_metres_per_pixel == null
        ? "Ground plane fitted. Speed in metres per second still needs a measured distance pair."
        : "Calibration complete. The ground plane and metric scale are ready.");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Could not fit calibration. Check the points and try again."); }
    finally { setFitting(false); }
  };

  if (loading) return <main style={{ padding: 32 }}>Loading calibration…</main>;
  const frameUrl = media ? mediaApi.streamUrl(caseId, mediaId) : null;
  const complete = !!fit;
  const step = complete ? 3 : anchors.length >= 5 ? 2 : 1;

  return (
    <main className="calibration-page" style={{ maxWidth: 1440, margin: "0 auto", padding: "24px clamp(16px, 3vw, 40px) 48px", color: "var(--text-primary)" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 22 }}>
        <Link href={`/cases/${caseId}`} className="btn btn-ghost" style={{ padding: "6px 10px" }}>← Case</Link>
        <div><h1 className="heading-sm" style={{ margin: 0 }}>Calibrate this camera</h1><p className="text-sm text-tertiary" style={{ margin: "4px 0 0" }}>{media?.original_filename}</p></div>
      </header>

      <section className="card" style={{ padding: "18px 20px", marginBottom: 18, borderLeft: "4px solid var(--sky-mid)" }}>
        <strong>Advanced reviewer tool · most clips don’t need this</strong>
        <p style={{ margin: "6px 0 10px", lineHeight: 1.55 }}>This optional setup is only for a stationary camera with measured road points. It is not required to upload a clip, review tracks, or compare what is visible in the video. To estimate physical speed, four measured points define the mapping and a fifth measured point independently checks it. Choose one point as (0, 0); measure all coordinates from the same origin.</p>
        <label style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: 14, lineHeight: 1.45 }}>
          <input type="checkbox" checked={cameraConfirmed} onChange={e => setCameraConfirmed(e.target.checked)} style={{ marginTop: 3 }} />
          This is a fixed camera and the points lie on the same flat road surface.
        </label>
        {!cameraConfirmed && <p style={{ color: "var(--sand-mid)", margin: "8px 0 0", fontSize: 13 }}>Moving dashcam footage changes camera position; this calibration method cannot give reliable ground-plane measurements for it.</p>}
      </section>

      <nav aria-label="Calibration steps" style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}>
        {["1. Add 5 measured road points", "2. Fit the ground plane", "3. Check the result"].map((label, i) => <div key={label} style={{ borderRadius: 999, padding: "8px 14px", fontSize: 13, background: step >= i + 1 ? "var(--sage-light)" : "var(--bg-secondary)", color: step >= i + 1 ? "var(--sage-dark)" : "var(--text-tertiary)" }}>{label}</div>)}
      </nav>

      <div className="calibration-layout" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.7fr) minmax(320px, 0.9fr)", gap: 18, alignItems: "start" }}>
        <section className="card" style={{ padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
            <strong>1. Pause and mark a road point</strong><span className="text-sm text-tertiary">{anchors.length} saved · need at least 5</span>
          </div>
          <p className="text-sm text-tertiary" style={{ margin: "0 0 12px" }}>Use the video controls to pause at a clear frame, then freeze it. Mark the first four measured road points, then mark a fifth independently measured point to check the result.</p>
          <div style={{ background: "#111", borderRadius: 10, overflow: "hidden", lineHeight: 0 }}>
            {frameUrl && <video ref={videoRef} src={frameUrl} crossOrigin="use-credentials" preload="metadata" controls style={{ display: frozenFrame ? "none" : "block", width: "100%", height: "auto", margin: "0 auto" }} title="Pause at the frame you want to use" />}
            {frameUrl && frozenFrame && <div style={{ position: "relative", lineHeight: 0 }}>
              <img src={frozenFrame} onClick={handleFrameClick} style={{ display: "block", width: "100%", height: "auto", cursor: "crosshair" }} alt="Frozen video frame. Click to place a calibration point." />
              <svg viewBox={`0 0 ${media?.width ?? 1920} ${media?.height ?? 1080}`} preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
                {anchors.map((a, i) => <g key={a.id}><circle cx={a.pixel_x} cy={a.pixel_y} r={12} fill="#17824b" fillOpacity="0.85" stroke="white" strokeWidth={3} /><text x={a.pixel_x + 14} y={a.pixel_y - 10} fill="white" fontSize={30} fontWeight="700" stroke="#111" strokeWidth={3} paintOrder="stroke">{i + 1}</text></g>)}
                {pending && <g><circle cx={pending.pixel_x} cy={pending.pixel_y} r={13} fill="#0877d1" fillOpacity="0.85" stroke="white" strokeWidth={3} /><text x={pending.pixel_x + 15} y={pending.pixel_y - 10} fill="white" fontSize={30} fontWeight="700" stroke="#111" strokeWidth={3} paintOrder="stroke">{anchors.length + 1}</text></g>}
              </svg>
            </div>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
            {!frozenFrame ? <button className="btn btn-primary" onClick={freezeFrame} disabled={!media}>Freeze this frame to mark points</button> : <><span className="text-sm" style={{ color: "var(--sage-mid)" }}>Frame frozen · click the still image to place a point</span><button className="btn btn-ghost" onClick={() => { setFrozenFrame(null); setPending(null); }}>Choose another frame</button></>}
          </div>
          {!frozenFrame && <p className="text-sm text-tertiary" style={{ margin: "8px 0 0" }}>Pause on the frame you want, then press “Freeze this frame to mark points”.</p>}
          {pending && <div style={{ marginTop: 14, padding: 16, border: "1px solid var(--sky-mid)", borderRadius: 10, background: "var(--sky-light)" }}>
            <strong>Describe the selected point</strong><span className="text-sm text-tertiary"> · video pixel ({pending.pixel_x.toFixed(0)}, {pending.pixel_y.toFixed(0)})</span>
            <div className="calibration-point-fields" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
              <label style={{ fontSize: 13 }}>Point name<input style={inputStyle} value={pending.label} onChange={e => setPending(p => p && ({ ...p, label: e.target.value }))} placeholder="e.g. near-left stop-line corner" /></label>
              <div style={{ display: "flex", gap: 8, alignItems: "end", fontSize: 12, color: "var(--text-tertiary)" }}>Use a tape/GPS/site plan. X and Y must describe the same physical point shown in the video.</div>
              <label style={{ fontSize: 13 }}>X position (metres)<input style={inputStyle} type="number" step="any" value={pending.world_x} onChange={e => setPending(p => p && ({ ...p, world_x: e.target.value }))} placeholder="0" /></label>
              <label style={{ fontSize: 13 }}>Y position (metres)<input style={inputStyle} type="number" step="any" value={pending.world_y} onChange={e => setPending(p => p && ({ ...p, world_y: e.target.value }))} placeholder="0" /></label>
            </div>
            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", fontSize: 13 }}>I have a measured distance and need real speed units</summary>
              <p className="text-sm text-tertiary">Enter the measured straight-line distance for this first point to a second point you will mark later. On that second point, select “This is the other end”.</p>
              <label style={{ display: "block", fontSize: 13 }}>Distance to second point (metres)<input style={{ ...inputStyle, maxWidth: 240 }} type="number" min="0" step="any" value={pending.known_distance_m} onChange={e => setPending(p => p && ({ ...p, known_distance_m: e.target.value }))} placeholder="e.g. 8.5" /></label>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginTop: 8 }}><input type="checkbox" checked={pending.is_distance_ref_b} onChange={e => setPending(p => p && ({ ...p, is_distance_ref_b: e.target.checked }))} />This is the other end of the measured distance</label>
            </details>
            <div style={{ display: "flex", gap: 8, marginTop: 14 }}><button className="btn btn-primary" disabled={saving} onClick={() => void confirmAnchor()}>{saving ? "Saving…" : "Save point"}</button><button className="btn btn-ghost" onClick={() => setPending(null)}>Cancel</button></div>
          </div>}
        </section>

        <aside style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <section className="card" style={{ padding: 16 }}>
            <strong>2. Your marked points</strong>
            {anchors.length === 0 ? <p className="text-sm text-tertiary" style={{ marginBottom: 0 }}>This step is optional. If you need real-world speed, use measured points from a fixed-camera view; four set the mapping and the fifth checks it independently.</p> : <ol style={{ margin: "10px 0", paddingLeft: 22 }}>{anchors.map((a, i) => <li key={a.id} style={{ padding: "7px 0", borderBottom: "1px solid var(--border)" }}><div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><span><strong>{a.label}{i === 4 ? " · independent check" : i < 4 ? " · mapping point" : " · check point"}</strong><br /><small className="text-tertiary">X {a.world_x} m · Y {a.world_y} m</small></span><button aria-label={`Remove ${a.label}`} onClick={() => void deleteAnchor(a.id)} className="btn btn-ghost" style={{ padding: "2px 8px", alignSelf: "start" }}>Remove</button></div><small className="text-tertiary">Video point {i + 1}</small></li>)}</ol>}
            <button className="btn btn-primary" onClick={() => void fitHomography()} disabled={fitting || anchors.length < 5 || !cameraConfirmed} style={{ width: "100%", marginTop: 8 }}>{fitting ? "Checking calibration…" : anchors.length < 5 ? `Add ${5 - anchors.length} more measured point${5 - anchors.length === 1 ? "" : "s"}` : !cameraConfirmed ? "Confirm fixed camera to continue" : "Validate ground-plane mapping"}</button>
            {anchors.length >= 5 && !cameraConfirmed && <p className="text-sm text-tertiary" style={{ marginBottom: 0 }}>Only continue if this really is a fixed camera and all points lie on the same flat road surface.</p>}
          </section>

          {error && <div role="alert" className="alert alert-error">{error}</div>}
          {notice && <div role="status" className="card" style={{ padding: 14, borderLeft: "3px solid var(--sage-mid)", fontSize: 14 }}>{notice}</div>}

          {fit && <section className="card" style={{ padding: 16, borderLeft: `4px solid ${fit.reprojection_rmse_px <= 2 ? "var(--sage-mid)" : fit.reprojection_rmse_px <= 5 ? "var(--sand-mid)" : "var(--rose-mid)"}` }}>
            <strong>3. Calibration result</strong>
            <p style={{ fontSize: 20, margin: "10px 0 4px" }}>Independent check error: {fit.reprojection_rmse_px.toFixed(2)} px</p>
            <p className="text-sm text-tertiary" style={{ marginTop: 0 }}>{fit.reprojection_rmse_px <= 2 ? "The held-out point agrees with the mapping. This does not prove the road measurements are correct." : "The held-out check is close to the 5 px limit. Recheck the point and measurements before relying on physical values."}</p>
            {fit.scale_metres_per_pixel == null ? <p className="text-sm" style={{ marginBottom: 0 }}>Ground plane is fitted, but speed in m/s is unavailable until you add a known-distance pair and fit again.</p> : <p className="text-sm" style={{ marginBottom: 0 }}>Measured distance is included; metric speeds can be calculated under the stated assumptions.</p>}
          </section>}

          <section className="card" style={{ padding: 16, fontSize: 13, lineHeight: 1.55 }}>
            <strong>When this is appropriate</strong>
            <ul style={{ paddingLeft: 18, marginBottom: 0 }}><li>Use only a stationary camera; a moving dashcam changes viewpoint.</li><li>Road points must be on one flat plane.</li><li>Coordinates must come from actual measurements or a trusted site plan.</li><li>Four points fit the mapping; the fifth is an independent accuracy check.</li><li>Anchor residual is not proof the measurements are true; this is a reviewer aid, not a forensic certification.</li></ul>
          </section>
          <Link className="btn btn-ghost" href={`/cases/${caseId}/media/${mediaId}/tracks`}>Back to tracks</Link>
        </aside>
      </div>
    </main>
  );
}

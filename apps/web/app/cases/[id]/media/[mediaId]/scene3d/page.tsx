"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Scene3D from "@/components/scene3d/Scene3D";
import { phase5Api, type Scene3D as SceneData } from "@/lib/api";

export default function ScenePage() {
  const { id: caseId, mediaId } = useParams<{ id: string; mediaId: string }>();
  const [scene, setScene] = useState<SceneData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setScene(await phase5Api.scene(caseId, mediaId)); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [caseId, mediaId]);
  useEffect(() => { void load(); }, [load]);

  return (
    <main className="page-content scene-page fade-in">
      <div className="phase5-nav"><Link href={`/cases/${caseId}`}>← Back to case</Link><Link href={`/cases/${caseId}/phase5`}>Evidence &amp; exports →</Link></div>
      <header className="page-header">
        <p className="eyebrow">Phase 5 · 3D replay</p>
        <h1>Ground-plane scene</h1>
        <p>Positions come directly from stored engine coordinates. Drag to orbit, adjust elevation, or scrub observed track time.</p>
      </header>
      {error && <div className="alert alert-error mb-4" role="alert">{error}<button className="btn btn-secondary btn-sm" style={{ marginLeft: 12 }} onClick={() => void load()}>Retry</button></div>}
      {loading && <div className="card card-body flex items-center gap-3"><div className="spinner" /> Loading scene data…</div>}
      {!loading && scene && <>
        <section className="card card-body scene-page-card"><Scene3D scene={scene} /></section>
        <div className="scene-source-note"><strong>What this view can show</strong><span>Track positions in the calibrated ground plane, fitted paths, and labelled model scenarios.</span><strong>What this view does not infer</strong><span>Vehicle dimensions, height, camera pose, unseen surfaces, or legal fault.</span></div>
      </>}
    </main>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  casesApi, mediaApi, jobsApi,
  formatBytes, shortHash, relativeTime,
  type Case, type SourceMedia, type IntegrityCheck, type Job,
} from "@/lib/api";

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  draft:      { label: "Draft",      cls: "badge-neutral" },
  processing: { label: "Processing", cls: "badge-sky" },
  ready:      { label: "Ready",      cls: "badge-sage" },
  exported:   { label: "Exported",   cls: "badge-sand" },
};

const MEDIA_STATUS: Record<string, { label: string; cls: string }> = {
  uploading: { label: "Uploading…",  cls: "badge-sky" },
  stored:    { label: "Stored",      cls: "badge-sage" },
  probing:   { label: "Probing…",   cls: "badge-sky" },
  indexed:   { label: "Indexed",     cls: "badge-sage" },
  failed:    { label: "Failed",      cls: "badge-rose" },
};

interface UploadItem {
  file: File;
  progress: number;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
  result?: SourceMedia;
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [kase, setKase]       = useState<Case | null>(null);
  const [media, setMedia]     = useState<SourceMedia[]>([]);
  const [jobs, setJobs]       = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [integrity, setIntegrity] = useState<Record<string, IntegrityCheck>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, m, j] = await Promise.all([
        casesApi.get(id),
        mediaApi.list(id),
        jobsApi.listForCase(id),
      ]);
      setKase(c); setMedia(m); setJobs(j);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleFiles = async (files: FileList | File[]) => {
    const dropped = Array.from(files);
    const valid = dropped.filter(f => f.type.startsWith("video/"));
    if (dropped.length !== valid.length) setActionError("Choose a video file such as MP4, MOV, AVI, or WebM. Other file types were skipped.");
    const pendingCount = uploads.filter((item) => item.status === "pending" || item.status === "uploading").length;
    const slots = Math.max(0, 3 - media.length - pendingCount);
    setActionError(null);
    if (valid.length > slots) setActionError(`This case accepts up to 3 clips. Only ${slots} more ${slots === 1 ? "clip can" : "clips can"} be added.`);
    const arr = valid.slice(0, slots);
    if (!arr.length) return;

    const items: UploadItem[] = arr.map(f => ({ file: f, progress: 0, status: "pending" }));
    setUploads(prev => [...prev, ...items]);

    for (let i = 0; i < arr.length; i++) {
      const file = arr[i];
      setUploads(prev => prev.map(u => u.file === file ? { ...u, status: "uploading" } : u));
      try {
        const result = await mediaApi.upload(id, file, (pct) => {
          setUploads(prev => prev.map(u => u.file === file ? { ...u, progress: pct } : u));
        });
        setUploads(prev => prev.map(u => u.file === file ? { ...u, status: "done", progress: 100, result } : u));
        setMedia(prev => [...prev, result]);
      } catch (e: unknown) {
        setUploads(prev => prev.map(u => u.file === file ? { ...u, status: "error", error: (e as Error).message } : u));
      }
    }
  };

  const checkIntegrity = async (m: SourceMedia) => {
    try {
      const result = await mediaApi.checkIntegrity(id, m.id);
      setIntegrity(prev => ({ ...prev, [m.id]: result }));
    } catch (e) {
      setActionError(`Could not verify ${m.original_filename}: ${(e as Error).message}`);
    }
  };

  const retryUpload = (file: File) => {
    setUploads((previous) => previous.filter((item) => item.file !== file));
    void handleFiles([file]);
  };

  const deleteMedia = async (m: SourceMedia) => {
    if (!confirm(`Delete "${m.original_filename}"? This cannot be undone.`)) return;
    await mediaApi.delete(id, m.id);
    setMedia(prev => prev.filter(x => x.id !== m.id));
  };

  if (loading) return (
    <div className="main-with-sidebar">
      <SidebarShell caseId={id} />
      <div className="page-content flex items-center gap-3" style={{ color: "var(--slate-500)" }}>
        <div className="spinner" /> Loading case…
      </div>
    </div>
  );

  if (error || !kase) return (
    <div className="main-with-sidebar">
      <SidebarShell caseId={id} />
      <div className="page-content">
        <div className="alert alert-error">!  {error ?? "Case not found"}</div>
        <Link href="/cases" className="btn btn-secondary mt-4">← All Cases</Link>
      </div>
    </div>
  );

  const badge = STATUS_BADGE[kase.status] ?? { label: kase.status, cls: "badge-neutral" };
  const canUpload = media.length < 3;

  return (
    <div className="main-with-sidebar">
      <SidebarShell caseId={id} kaseTitle={kase.title} />

      <div className="page-content fade-in">
        {/* Header */}
        <div className="page-header">
          <div className="flex items-center gap-3 mb-4">
            <Link href="/cases" className="text-sm text-secondary" style={{ textDecoration: "none" }}>
              ← Cases
            </Link>
            <span className="text-secondary">/</span>
            <span className="text-sm" style={{ color: "var(--slate-700)" }}>{kase.title}</span>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 style={{ fontSize: "var(--text-2xl)" }}>{kase.title}</h1>
                <span className={`badge ${badge.cls}`}>{badge.label}</span>
              </div>
              {kase.incident_location && (
                <p className="text-sm text-secondary">{kase.incident_location}</p>
              )}
            </div>
          </div>
        </div>

        {/* Metadata bar */}
        <div className="card mb-6">
          <div className="card-body" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "var(--space-4)" }}>
            <MetaItem label="Case ID"    value={<span className="font-mono" style={{ fontSize: 11 }}>{kase.id.slice(0, 18)}…</span>} />
            <MetaItem label="Created"    value={relativeTime(kase.created_at)} />
            <MetaItem label="Jurisdiction" value={kase.jurisdiction ?? "—"} />
            <MetaItem label="Incident date" value={kase.incident_date ? new Date(kase.incident_date).toLocaleString() : "—"} />
            <MetaItem label="Consent"    value={kase.consent_given ? "Given ✓" : "Not given"} />
            <MetaItem label="Footage files" value={`${media.length} / 3`} />
          </div>
        </div>

        <div className="phase5-entry card mb-6">
          {media.length === 0 ? <><div><strong>Start with the footage</strong><p className="text-sm text-secondary mt-1">Add a clip to preserve the original and begin reviewing what it shows.</p></div><Link href="#source-media" className="btn btn-primary">Add footage <span aria-hidden="true">↓</span></Link></> : <><div><strong>Your footage is ready to review</strong><p className="text-sm text-secondary mt-1">Compare clips, add source-linked observations, or prepare a traceable report.</p></div><div className="flex gap-2" style={{ flexWrap: "wrap" }}><Link href={`/cases/${id}/review-workspace`} className="btn btn-primary">Review footage <span aria-hidden="true">→</span></Link><Link href={`/cases/${id}/reports`} className="btn btn-secondary">Evidence &amp; reports</Link></div></>}
        </div>

        {actionError && <div className="alert alert-error mb-4" role="alert"><span>{actionError}</span><button className="btn btn-ghost btn-sm" onClick={() => setActionError(null)}>Dismiss</button></div>}

        {/* Source Media */}
        <section id="source-media">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 style={{ fontSize: "var(--text-xl)" }}>Original footage</h2>
              <p className="text-sm text-secondary mt-2">
                Original bytes stored unchanged. SHA-256 verified on every re-download.
              </p>
              <p className="text-sm text-secondary mt-1">Upload and review clips without measuring the scene. Physical speed and distance are optional and may be unavailable for moving or uncalibrated footage.</p>
            </div>
          </div>

          {/* Upload zone */}
          {canUpload && (
            <div
              className={`upload-zone mb-6 ${dragOver ? "drag-over" : ""}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
              role="button"
              tabIndex={0}
              aria-label="Upload video clips"
              onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="video/mp4,video/quicktime,video/x-msvideo,video/webm"
                multiple
                style={{ display: "none" }}
                onChange={(e) => e.target.files && handleFiles(e.target.files)}
              />
              <div className="upload-icon">
                <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M24 8v24M16 16l8-8 8 8M8 36h32" strokeLinecap="round" />
                </svg>
              </div>
              <h3>Choose video clips or drag them here</h3>
              <p>MP4, MOV, AVI, WebM · up to 500 MB each · {3 - media.length} upload slot{3 - media.length !== 1 ? "s" : ""} available</p>
            </div>
          )}

          {!canUpload && (
            <div className="alert alert-info mb-4">
              <span>i </span>
              Maximum 3 clips per case. Remove a clip to add another.
            </div>
          )}

          {/* Upload progress items */}
          {uploads.filter(u => u.status !== "done").map((u, i) => (
            <div key={i} className="card mb-3">
              <div className="card-body">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">{u.file.name}</span>
                  <span className={`badge ${u.status === "error" ? "badge-rose" : "badge-sky"}`}>
                    {u.status === "error" ? "Upload failed" : u.status === "done" ? "Saved" : `${u.progress}%`}
                  </span>
                </div>
                {u.status === "error" && <div className="upload-error-row"><span>{u.error || "The connection was interrupted."} Your original file is still on this device.</span><button className="btn btn-secondary btn-sm" onClick={() => retryUpload(u.file)}>Retry upload</button></div>}
                {u.status === "uploading" && (
                  <div className="progress-bar">
                    <div className="progress-bar-fill" style={{ width: `${u.progress}%` }} />
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Media table */}
          {media.length > 0 && (
            <div className="card">
              <div className="table-container" style={{ borderRadius: "var(--radius-lg)", boxShadow: "none" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Original clip</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Integrity</th>
                      <th><span className="sr-only">Clip options</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {media.map((m) => {
                      const ms = MEDIA_STATUS[m.status] ?? { label: m.status, cls: "badge-neutral" };
                      const integ = integrity[m.id];
                      return (
                        <tr key={m.id}>
                          <td>
                            <div style={{ fontWeight: 500 }}>{m.original_filename}</div>
                            <div className="text-xs text-secondary">{formatBytes(m.byte_length)} · Added {relativeTime(m.upload_time)}</div>
                          </td>
                          <td><span className={`badge ${ms.cls}`}>{ms.label}</span></td>
                          <td className="text-sm">
                            {m.duration_seconds != null ? `${m.duration_seconds.toFixed(1)}s` : "—"}
                          </td>
                          <td>
                            {integ ? (
                              integ.intact
                                ? <span className="badge badge-sage">✓ Intact</span>
                                : <span className="badge badge-rose">✗ Mismatch</span>
                            ) : (
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => checkIntegrity(m)}
                              >
                                Verify
                              </button>
                            )}
                          </td>
                          <td>
                            <details className="media-more"><summary>Options</summary><div className="media-more-menu">
                              <button className="media-option" onClick={() => mediaApi.downloadOriginal(id, m.id, m.original_filename)}>Download original</button>
                              <button className="media-option" onClick={() => navigator.clipboard.writeText(m.sha256)}>Copy source SHA-256</button>
                              <span className="media-hash" title={m.sha256}>Source SHA-256 · {shortHash(m.sha256)} · {m.codec ?? "Codec unavailable"} · {m.is_variable_framerate == null ? "Frame rate unknown" : m.is_variable_framerate ? "Variable frame rate" : "Constant frame rate"}</span>
                              <Link className="media-option" href={`/cases/${id}/media/${m.id}/tracks`}>Review detected tracks</Link>
                              <Link className="media-option" href={`/cases/${id}/media/${m.id}/scene3d`}>Open 3D replay</Link>
                              <details className="media-advanced"><summary>Advanced motion analysis</summary><div className="media-option-list"><Link className="media-option" href={`/cases/${id}/media/${m.id}/calibration`}>Set scene scale</Link><Link className="media-option" href={`/cases/${id}/media/${m.id}/dynamics`}>View motion report</Link></div></details>
                              {m.status === "failed" && <button className="media-option" onClick={async () => { await mediaApi.retry(id, m.id); await refresh(); }}>Retry processing</button>}
                              <button className="media-option danger" onClick={() => deleteMedia(m)}>Remove clip</button>
                            </div></details>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {media.length === 0 && uploads.length === 0 && (
            <div className="empty-state" style={{ padding: "var(--space-10) 0" }}>
              <div className="empty-state-icon">＋</div>
              <h3>No clips yet</h3>
              <p>Upload up to three clips. You can still review footage when exact speed or distance cannot be measured.</p>
            </div>
          )}
        </section>

        {/* Processing Log */}
        {jobs.length > 0 && (
          <section className="mt-8">
            <h2 style={{ fontSize: "var(--text-xl)", marginBottom: "var(--space-4)" }}>
              Processing Log
            </h2>
            <div className="card">
              <div className="table-container" style={{ borderRadius: "var(--radius-lg)", boxShadow: "none" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Processing step</th>
                      <th>Status</th>
                      <th>Progress</th>
                      <th>Queued</th>
                      <th>Completed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.id}>
                        <td className="text-sm">{jobLabel(j.stage)}</td>
                        <td>
                          <span className={`badge ${
                            j.status === "done" ? "badge-sage" :
                            j.status === "failed" ? "badge-rose" :
                            j.status === "running" ? "badge-sky" : "badge-neutral"
                          }`}>{j.status}</span>
                        </td>
                        <td>
                          <div className="progress-bar" style={{ width: 80 }}>
                            <div className="progress-bar-fill" style={{ width: `${j.progress}%` }} />
                          </div>
                        </td>
                        <td className="text-sm text-secondary">{relativeTime(j.queued_at)}</td>
                        <td className="text-sm text-secondary">
                          {j.completed_at ? relativeTime(j.completed_at) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {/* Description */}
        {kase.description && (
          <section className="mt-8">
            <h2 style={{ fontSize: "var(--text-xl)", marginBottom: "var(--space-4)" }}>Notes</h2>
            <div className="card">
              <div className="card-body">
                <p className="text-sm" style={{ color: "var(--slate-600)", lineHeight: 1.7 }}>
                  {kase.description}
                </p>
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--slate-400)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>
        {label}
      </div>
      <div className="text-sm" style={{ color: "var(--slate-800)" }}>{value}</div>
    </div>
  );
}

function jobLabel(stage: string) {
  const labels: Record<string, string> = {
    ingest: "Preparing original clip",
    probe: "Reading video details",
    media_probe: "Reading video details",
    tracking: "Finding visible objects",
    transcription: "Transcribing speech",
    claim_extraction: "Preparing statement claims",
    dynamics: "Estimating motion",
    export: "Preparing case report",
  };
  return labels[stage] ?? stage.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function SidebarShell({ caseId, kaseTitle }: { caseId: string; kaseTitle?: string }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">
          <div className="sidebar-logo-box">BB</div>
          <div>
            <div className="sidebar-logo-name">Blackbox</div>
            <div className="sidebar-logo-sub">Evidence workspace</div>
          </div>
        </div>
      </div>
      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Workspace</div>
        <Link href="/cases" className="nav-item">
          <span className="nav-item-icon">▤</span> Cases
        </Link>
        <Link href="/cases/new" className="nav-item">
          <span className="nav-item-icon">＋</span> New Case
        </Link>
        {kaseTitle && (
          <>
            <div className="sidebar-section-label" style={{ marginTop: "var(--space-4)" }}>This Case</div>
            <Link href={`/cases/${caseId}`} className="nav-item active">
              <span className="nav-item-icon">◉</span>
              <span className="truncate" style={{ maxWidth: 160 }}>{kaseTitle}</span>
            </Link>
            <Link href={`/cases/${caseId}/transcripts`} className="nav-item">
              <span className="nav-item-icon">≡</span> Transcripts
            </Link>
            <Link href={`/cases/${caseId}/claims`} className="nav-item">
              <span className="nav-item-icon">◈</span> Claims
            </Link>
            <Link href={`/cases/${caseId}/reports`} className="nav-item">
              <span className="nav-item-icon">▧</span> Evidence &amp; reports
            </Link>
          </>
        )}
      </nav>
      <div className="sidebar-footer">Evidence review workspace</div>
    </aside>
  );
}

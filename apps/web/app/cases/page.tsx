"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { casesApi, relativeTime, type Case } from "@/lib/api";

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  draft:      { label: "Draft",      cls: "badge-neutral" },
  processing: { label: "Processing", cls: "badge-sky" },
  ready:      { label: "Ready",      cls: "badge-sage" },
  exported:   { label: "Exported",   cls: "badge-sand" },
};

export default function CasesPage() {
  const [cases, setCases]   = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    casesApi.list()
      .then(setCases)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="main-with-sidebar">
      <Sidebar active="cases" />

      <div className="page-content fade-in">
        <div className="page-header flex items-center justify-between">
          <div>
            <h1>Cases</h1>
            <p>Each case is an independent investigation. Originals are preserved on creation.</p>
          </div>
          <Link href="/cases/new" className="btn btn-primary">
            + New Case
          </Link>
        </div>

        {loading && (
          <div className="flex items-center gap-3" style={{ color: "var(--slate-500)", padding: "var(--space-8) 0" }}>
            <div className="spinner" />
            Loading cases…
          </div>
        )}

        {error && (
          <div className="alert alert-error">
            <span>⚠</span> {error}
          </div>
        )}

        {!loading && !error && cases.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">📁</div>
            <h3>No cases yet</h3>
            <p>Create your first case to start preserving and analysing incident footage.</p>
            <Link href="/cases/new" className="btn btn-primary">Open a Case</Link>
          </div>
        )}

        {!loading && cases.length > 0 && (
          <>
            <div className="stat-grid mb-6">
              <StatCard label="Total Cases"    value={cases.length} sub="all time" />
              <StatCard label="Ready"          value={cases.filter(c => c.status === "ready").length}      sub="analysis complete" />
              <StatCard label="Processing"     value={cases.filter(c => c.status === "processing").length} sub="in pipeline" />
              <StatCard label="Total Clips"    value={cases.reduce((a, c) => a + c.media_count, 0)}        sub="source media files" />
            </div>

            <div className="card">
              <div className="card-header">
                <span style={{ color: "var(--slate-500)", fontSize: "var(--text-sm)" }}>
                  {cases.length} case{cases.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="table-container" style={{ borderRadius: 0, border: "none", boxShadow: "none" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Status</th>
                      <th>Clips</th>
                      <th>Location</th>
                      <th>Created</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {cases.map((c) => {
                      const badge = STATUS_BADGE[c.status] ?? { label: c.status, cls: "badge-neutral" };
                      return (
                        <tr key={c.id}>
                          <td>
                            <Link href={`/cases/${c.id}`} style={{ fontWeight: 500, color: "var(--slate-900)" }}>
                              {c.title}
                            </Link>
                            {c.description && (
                              <div className="text-xs text-secondary truncate" style={{ maxWidth: 260, marginTop: 2 }}>
                                {c.description}
                              </div>
                            )}
                          </td>
                          <td><span className={`badge ${badge.cls}`}>{badge.label}</span></td>
                          <td>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}>
                              {c.media_count} / 3
                            </span>
                          </td>
                          <td className="text-sm text-secondary">{c.incident_location ?? "—"}</td>
                          <td className="text-sm text-secondary">{relativeTime(c.created_at)}</td>
                          <td>
                            <Link href={`/cases/${c.id}`} className="btn btn-secondary btn-sm">
                              Open →
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}

function Sidebar({ active }: { active: string }) {
  const nav = [
    { href: "/cases",    icon: "📁", label: "Cases" },
    { href: "/cases/new", icon: "＋", label: "New Case" },
  ];
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
        {nav.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className={`nav-item ${active === n.label.toLowerCase().replace(" ", "-") ? "active" : ""}`}
          >
            <span className="nav-item-icon">{n.icon}</span>
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer">Phase 1 · Evidence Foundation</div>
    </aside>
  );
}

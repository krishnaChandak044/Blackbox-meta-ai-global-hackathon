"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { casesApi, relativeTime, type Case } from "@/lib/api";

const STATUS: Record<string, string> = { draft: "Draft", processing: "Processing", ready: "Ready", exported: "Exported" };

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const load = () => {
    setLoading(true); setError("");
    casesApi.list().then(setCases).catch((e: Error) => setError(e.message)).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cases.filter((item) => !q || [item.title, item.description, item.incident_location, item.jurisdiction].some((v) => v?.toLowerCase().includes(q)));
  }, [cases, query]);

  return <div className="main-with-sidebar">
    <aside className="sidebar">
      <Link href="/" className="sidebar-logo brand-lockup"><span className="brand-mark">B</span><span><strong>Blackbox</strong><small>Evidence workspace</small></span></Link>
      <nav className="sidebar-nav" aria-label="Workspace">
        <div className="sidebar-section-label">Workspace</div>
        <Link href="/cases" className="nav-item active"><span className="nav-glyph">▤</span>Cases</Link>
        <Link href="/cases/new" className="nav-item"><span className="nav-glyph">＋</span>New case</Link>
      </nav>
      <div className="sidebar-footer"><span className="status-dot" /> Evidence review workspace</div>
    </aside>

    <main className="page-content cases-page fade-in">
      <header className="page-header cases-heading">
        <div><p className="eyebrow">Workspace / Cases</p><h1>Your cases</h1><p>Open an investigation or continue reviewing a saved case.</p></div>
        <Link href="/cases/new" className="btn btn-primary">＋ <span>New case</span></Link>
      </header>

      <section className="case-list-panel" aria-label="Case list">
        <div className="case-list-toolbar">
          <div><h2>All cases</h2><p>{loading ? "Loading your workspace…" : `${cases.length} ${cases.length === 1 ? "case" : "cases"}`}</p></div>
          {!loading && cases.length > 0 && <label className="case-search"><span aria-hidden="true">⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by title or location" aria-label="Search cases" /></label>}
        </div>
        {error && <div className="case-error" role="alert"><div><strong>Cases couldn’t load.</strong><span>{error}</span></div><button className="btn btn-secondary btn-sm" onClick={load}>Try again</button></div>}
        {loading && <div className="case-loading"><span className="spinner" /> Connecting to your workspace…</div>}
        {!loading && !error && cases.length === 0 && <div className="case-empty"><span className="empty-mark">B</span><h3>No cases yet</h3><p>Create a case to preserve source footage and begin a structured review. You can add video after the case is created.</p><Link href="/cases/new" className="btn btn-primary">Open your first case <span aria-hidden="true">→</span></Link></div>}
        {!loading && !error && cases.length > 0 && visible.length === 0 && <div className="case-empty compact"><h3>No matching cases</h3><p>Try another title, location, or jurisdiction.</p><button className="btn btn-secondary" onClick={() => setQuery("")}>Clear search</button></div>}
        {!loading && !error && visible.length > 0 && <div className="case-table-wrap"><table className="case-table"><thead><tr><th>Case</th><th>Status</th><th>Source clips</th><th>Location</th><th>Updated</th><th><span className="sr-only">Open case</span></th></tr></thead><tbody>{visible.map((item) => <tr key={item.id}>
          <td><Link className="case-title" href={`/cases/${item.id}`}>{item.title}</Link>{item.description && <span className="case-description">{item.description}</span>}</td>
          <td><span className={`case-status status-${item.status}`}>{STATUS[item.status] ?? item.status}</span></td>
          <td><span className="clip-count">{item.media_count}<span> / 3</span></span></td>
          <td className="case-muted">{item.incident_location || "Not added"}</td>
          <td className="case-muted">{relativeTime(item.created_at)}</td>
          <td><Link className="case-open-link" href={`/cases/${item.id}`} aria-label={`Open ${item.title}`}>Open <span aria-hidden="true">→</span></Link></td>
        </tr>)}</tbody></table></div>}
      </section>
      <p className="workspace-footnote"><span className="status-dot" /> Original media integrity and processing history are recorded per case.</p>
    </main>
  </div>;
}

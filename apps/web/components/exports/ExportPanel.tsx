"use client";

import { useCallback, useEffect, useState } from "react";
import { phase5Api, type CaseExport } from "@/lib/api";

export default function ExportPanel({ caseId }: { caseId: string }) {
  const [exports, setExports] = useState<CaseExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { setExports(await phase5Api.listExports(caseId)); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [caseId]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!exports.some((item) => item.status === "queued" || item.status === "running")) return;
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [exports, refresh]);

  const create = async () => {
    setCreating(true); setError(null); setNotice(null);
    try {
      const queued = await phase5Api.createExport(caseId);
      setNotice(`Export queued for case revision ${queued.case_revision_hash.slice(0, 12)}…`);
      await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setCreating(false); }
  };

  const download = async (item: CaseExport, kind: "pdf" | "json") => {
    try { await phase5Api.downloadExport(caseId, item.export_id, kind); }
    catch (e) { setError((e as Error).message); }
  };

  return (
    <section aria-labelledby="export-heading">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div><p className="eyebrow">Case package</p><h2 id="export-heading">PDF + JSON exports</h2><p className="text-sm text-secondary mt-2">Each export records an exact case revision, rechecks original media bytes, and keeps its own artifact hashes.</p></div>
        <button className="btn btn-primary" onClick={() => void create()} disabled={creating}>{creating ? "Queueing…" : "Create export"}</button>
      </div>
      {error && <div className="alert alert-error mb-4" role="alert">{error}</div>}
      {notice && <div className="alert alert-info mb-4" role="status">{notice}</div>}
      {loading ? <p className="text-sm text-secondary">Loading export history…</p> : exports.length === 0 ? (
        <div className="empty-state"><h3>No exports yet</h3><p>Create a review package after examining the available case data.</p></div>
      ) : <div className="export-list">{exports.map((item) => <article className="card export-card" key={item.export_id}>
        <div className="card-body">
          <div className="export-card-head"><div><span className={`badge ${item.status === "complete" ? "badge-sage" : item.status === "failed" || item.status === "stale" ? "badge-rose" : "badge-sky"}`}>{item.status}</span><p className="font-mono text-xs mt-2">{item.export_id}</p></div><span className="text-xs text-secondary">{new Date(item.created_at).toLocaleString()}</span></div>
          {item.error_message && <p className="text-sm" style={{ color: "var(--rose)" }}>{item.error_message}</p>}
          <dl className="export-hashes">
            <div><dt>Case revision</dt><dd title={item.case_revision_hash}>{item.case_revision_hash}</dd></div>
            {item.manifest_sha256 && <div><dt>Manifest</dt><dd title={item.manifest_sha256}>{item.manifest_sha256}</dd></div>}
            {item.pdf_sha256 && <div><dt>PDF SHA-256</dt><dd title={item.pdf_sha256}>{item.pdf_sha256}</dd></div>}
            {item.json_sha256 && <div><dt>JSON SHA-256</dt><dd title={item.json_sha256}>{item.json_sha256}</dd></div>}
          </dl>
          {item.status === "complete" && <div className="flex gap-2 mt-3"><button className="btn btn-secondary btn-sm" onClick={() => void download(item, "pdf")}>Download PDF</button><button className="btn btn-secondary btn-sm" onClick={() => void download(item, "json")}>Download JSON</button></div>}
        </div>
      </article>)}</div>}
    </section>
  );
}

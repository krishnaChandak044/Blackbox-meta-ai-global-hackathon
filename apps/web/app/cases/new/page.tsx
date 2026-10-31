"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { casesApi } from "@/lib/api";

const STEPS = ["Details", "Consent", "Review"];

export default function NewCasePage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    jurisdiction: "",
    incident_date: "",
    incident_location: "",
    consent_given: false,
  });

  const set = (k: string, v: string | boolean) =>
    setForm((prev) => ({ ...prev, [k]: v }));

  const canNext = () => {
    if (step === 0) return form.title.trim().length >= 3;
    if (step === 1) return form.consent_given;
    return true;
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const created = await casesApi.create({
        title: form.title,
        description: form.description || undefined,
        jurisdiction: form.jurisdiction || undefined,
        incident_date: form.incident_date || undefined,
        incident_location: form.incident_location || undefined,
        consent_given: form.consent_given,
      });
      router.push(`/cases/${created.id}`);
    } catch (e: unknown) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  };

  return (
    <div className="main-with-sidebar">
      <Sidebar />
      <div className="page-content fade-in" style={{ maxWidth: 680 }}>
        <div className="page-header">
          <h1>Open a New Case</h1>
          <p>Create the investigation record. You will upload media on the next screen.</p>
        </div>

        {/* Step indicator */}
        <div className="steps mb-6">
          {STEPS.map((label, i) => (
            <div className="step-item" key={label}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <div className={`step-circle ${i < step ? "done" : i === step ? "active" : ""}`}>
                  {i < step ? "✓" : i + 1}
                </div>
                <span className={`step-label ${i === step ? "active" : ""}`}>{label}</span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`step-line ${i < step ? "done" : ""}`} />
              )}
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-body">
            {step === 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                <div className="form-group">
                  <label className="form-label" htmlFor="title">Case title <span style={{color:"var(--rose)"}}>*</span></label>
                  <input
                    id="title"
                    className="form-input"
                    placeholder="e.g. Junction A14 — near-miss 29 Oct 2026"
                    value={form.title}
                    onChange={(e) => set("title", e.target.value)}
                    autoFocus
                    maxLength={255}
                  />
                  <span className="form-hint">Use a neutral, non-judgmental description.</span>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="description">Description</label>
                  <textarea
                    id="description"
                    className="form-textarea"
                    placeholder="Brief summary of what happened and what you're trying to determine…"
                    value={form.description}
                    onChange={(e) => set("description", e.target.value)}
                  />
                </div>

                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label" htmlFor="date">Incident date</label>
                    <input
                      id="date"
                      type="datetime-local"
                      className="form-input"
                      value={form.incident_date}
                      onChange={(e) => set("incident_date", e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="jurisdiction">Jurisdiction</label>
                    <input
                      id="jurisdiction"
                      className="form-input"
                      placeholder="e.g. Maharashtra, India"
                      value={form.jurisdiction}
                      onChange={(e) => set("jurisdiction", e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="location">Incident location</label>
                  <input
                    id="location"
                    className="form-input"
                    placeholder="e.g. NH-48 near Pune — intersection with Market Road"
                    value={form.incident_location}
                    onChange={(e) => set("incident_location", e.target.value)}
                  />
                </div>
              </div>
            )}

            {step === 1 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                <div className="alert alert-info">
                  <span>ℹ</span>
                  <div>
                    <strong>Before you upload:</strong> Blackbox stores the original bytes of any
                    file you upload. It will compute a SHA-256 hash and log every
                    transformation. Only you can access this case unless you share it explicitly.
                  </div>
                </div>

                <div className="card" style={{ background: "var(--sand-xlight)", borderColor: "var(--sand-mid)" }}>
                  <div className="card-body">
                    <h3 style={{ marginBottom: "var(--space-4)", fontSize: "var(--text-base)" }}>
                      What Blackbox will do with your media
                    </h3>
                    {[
                      "Store original bytes unchanged, compute SHA-256, and link every derived file back to the original.",
                      "Extract frame timestamps, codec, and metadata. Never transcode or alter the original.",
                      "Queue AI analysis jobs only when you explicitly request them.",
                      "Keep all data private to this case unless you generate a share link.",
                    ].map((item) => (
                      <div key={item} className="flex gap-3" style={{ marginBottom: "var(--space-3)", fontSize: "var(--text-sm)", color: "var(--slate-600)" }}>
                        <span style={{ color: "var(--sage)", flexShrink: 0 }}>✓</span>
                        {item}
                      </div>
                    ))}
                  </div>
                </div>

                <label
                  className="card"
                  style={{
                    cursor: "pointer",
                    borderColor: form.consent_given ? "var(--sage-mid)" : "var(--border)",
                    background: form.consent_given ? "var(--sage-xlight)" : "var(--bg-card)",
                    transition: "all var(--duration-md)",
                  }}
                >
                  <div className="card-body flex gap-4 items-start">
                    <input
                      type="checkbox"
                      checked={form.consent_given}
                      onChange={(e) => set("consent_given", e.target.checked)}
                      style={{ width: 18, height: 18, marginTop: 2, flexShrink: 0, accentColor: "var(--sage)" }}
                    />
                    <div>
                      <div style={{ fontWeight: 500, marginBottom: "var(--space-1)" }}>
                        I confirm I have the right to upload this footage
                      </div>
                      <div className="text-sm text-secondary">
                        The footage does not contain material that violates anyone&apos;s rights.
                        I understand Blackbox stores original bytes and logs all processing.
                      </div>
                    </div>
                  </div>
                </label>
              </div>
            )}

            {step === 2 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <h3 style={{ marginBottom: "var(--space-2)" }}>Review before creating</h3>

                <ReviewRow label="Title"     value={form.title} />
                <ReviewRow label="Description" value={form.description || "—"} />
                <ReviewRow label="Date"      value={form.incident_date || "—"} />
                <ReviewRow label="Location"  value={form.incident_location || "—"} />
                <ReviewRow label="Jurisdiction" value={form.jurisdiction || "—"} />
                <ReviewRow label="Consent"   value={form.consent_given ? "Given ✓" : "Not given"} />

                <div className="alert alert-success" style={{ marginTop: "var(--space-2)" }}>
                  <span>✓</span>
                  Creating this case will immediately generate a case ID and SHA-256 manifest.
                  You will be taken to the case page to upload video clips.
                </div>

                {error && (
                  <div className="alert alert-error">
                    <span>⚠</span> {error}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="card-footer flex justify-between items-center">
            <div>
              {step > 0 && (
                <button className="btn btn-ghost" onClick={() => setStep(s => s - 1)}>
                  ← Back
                </button>
              )}
              {step === 0 && (
                <Link href="/cases" className="btn btn-ghost">Cancel</Link>
              )}
            </div>
            <div className="flex gap-3">
              {step < STEPS.length - 1 ? (
                <button
                  className="btn btn-primary"
                  disabled={!canNext()}
                  onClick={() => setStep(s => s + 1)}
                >
                  Continue →
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  disabled={submitting}
                  onClick={submit}
                >
                  {submitting ? <><span className="spinner" /> Creating…</> : "Create Case →"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-4" style={{ borderBottom: "1px solid var(--border)", paddingBottom: "var(--space-3)" }}>
      <span className="text-sm" style={{ color: "var(--slate-500)", width: 120, flexShrink: 0 }}>{label}</span>
      <span className="text-sm" style={{ color: "var(--slate-900)", fontWeight: 400 }}>{value}</span>
    </div>
  );
}

function Sidebar() {
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
          <span className="nav-item-icon">📁</span> Cases
        </Link>
        <Link href="/cases/new" className="nav-item active">
          <span className="nav-item-icon">＋</span> New Case
        </Link>
      </nav>
      <div className="sidebar-footer">Phase 1 · Evidence Foundation</div>
    </aside>
  );
}

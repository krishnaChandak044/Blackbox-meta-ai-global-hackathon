"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import RadarPanel from "@/components/evidence-rescue/RadarPanel";
import AtlasPanel from "@/components/atlas/AtlasPanel";
import ExportPanel from "@/components/exports/ExportPanel";

export default function Phase5Page() {
  const { id } = useParams<{ id: string }>();
  return (
    <main className="page-content phase5-page fade-in">
      <div className="phase5-nav"><Link href={`/cases/${id}`}>← Back to case</Link><span>Phase 5 · Review tools</span></div>
      <header className="page-header">
        <p className="eyebrow">Case review</p>
        <h1>Evidence collection &amp; reporting</h1>
        <p>Inspect what is missing, review consented aggregate patterns, and create a traceable export.</p>
      </header>
      <div className="phase5-sections">
        <div className="card card-body"><RadarPanel caseId={id} /></div>
        <div className="card card-body"><AtlasPanel caseId={id} /></div>
        <div className="card card-body"><ExportPanel caseId={id} /></div>
      </div>
    </main>
  );
}

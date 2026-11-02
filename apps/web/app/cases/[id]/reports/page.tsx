"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import RadarPanel from "@/components/evidence-rescue/RadarPanel";
import AtlasPanel from "@/components/atlas/AtlasPanel";
import ExportPanel from "@/components/exports/ExportPanel";

export default function ReportsPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <main className="page-content phase5-page fade-in">
      <div className="phase5-nav"><Link href={`/cases/${id}`}>← Back to case</Link><span>Case review</span></div>
      <header className="page-header">
        <p className="eyebrow">Case review</p>
        <h1>Evidence &amp; reports</h1>
        <p>Keep track of useful follow-up evidence, review optional privacy-protected summaries, and create a traceable case package.</p>
      </header>
      <div className="phase5-sections">
        <div className="card card-body"><RadarPanel caseId={id} /></div>
        <div className="card card-body"><AtlasPanel caseId={id} /></div>
        <div className="card card-body"><ExportPanel caseId={id} /></div>
      </div>
    </main>
  );
}

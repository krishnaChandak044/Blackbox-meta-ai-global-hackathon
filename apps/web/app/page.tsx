import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="home-page">
      <header className="home-nav">
        <Link href="/" className="brand-lockup" aria-label="Blackbox home">
          <span className="brand-mark">B</span>
          <span><strong>Blackbox</strong><small>Evidence workspace</small></span>
        </Link>
        <nav aria-label="Main navigation">
          <Link href="/cases">Cases</Link>
          <Link className="btn btn-primary" href="/cases/new">Open a case <span aria-hidden="true">→</span></Link>
        </nav>
      </header>

      <section className="home-hero">
        <div className="home-copy">
          <p className="home-kicker"><span className="status-dot" /> Road incident evidence review</p>
          <h1>Make the footage<br />easier to understand.</h1>
          <p className="home-lede">Keep original clips intact. Review what is visible, compare accounts with cited evidence, and export a clear record of what is known and what remains uncertain.</p>
          <div className="home-actions">
            <Link href="/cases/new" className="btn btn-primary btn-lg">Start a case <span aria-hidden="true">→</span></Link>
            <Link href="/cases" className="home-text-link">Browse cases</Link>
          </div>
          <p className="home-caveat">Blackbox organizes evidence for human review. It does not determine legal fault or replace a qualified investigator.</p>
        </div>
        <aside className="home-brief" aria-label="Evidence handling principles">
          <div className="brief-topline"><span>WORKFLOW NOTE</span><span>01 / 03</span></div>
          <div className="brief-rule"><span /></div>
          <p className="brief-quote">Start with the source.<br />Keep every conclusion traceable.</p>
          <dl>
            <div><dt>01</dt><dd>Original media stays unchanged</dd></div>
            <div><dt>02</dt><dd>Observations stay distinct from assumptions</dd></div>
            <div><dt>03</dt><dd>Unclear evidence stays unresolved</dd></div>
          </dl>
        </aside>
      </section>

      <section className="home-process" aria-label="How Blackbox works">
        <div className="process-heading"><p className="eyebrow">A clear path through the evidence</p><h2>From source clip to reviewable record</h2></div>
        <div className="process-steps">
          <article><span>01</span><h3>Preserve</h3><p>Upload up to three clips. Blackbox records file integrity and keeps the original available.</p></article>
          <article><span>02</span><h3>Review</h3><p>Move through the footage, compare clips, and add notes tied to a source moment.</p></article>
          <article><span>03</span><h3>Share responsibly</h3><p>Export a traceable package that includes methods, assumptions, and limitations.</p></article>
        </div>
      </section>

      <footer className="home-footer"><span>BLACKBOX · EVIDENCE REVIEW</span><span>Human review stays in control.</span></footer>
    </main>
  );
}

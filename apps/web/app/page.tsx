import Link from "next/link";
import styles from "./page.module.css";

export default function LandingPage() {
  return (
    <main className="landing">
      <style>{`
        .landing {
          min-height: 100vh;
          background: var(--bg-page);
          display: flex;
          flex-direction: column;
        }

        /* ── Nav ── */
        .landing-nav {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--space-5) var(--space-10);
          border-bottom: 1px solid var(--border);
          background: var(--bg-card);
          position: sticky;
          top: 0;
          z-index: 50;
        }
        .nav-logo {
          display: flex;
          align-items: center;
          gap: var(--space-3);
          text-decoration: none !important;
        }
        .nav-logo-box {
          width: 34px; height: 34px;
          background: var(--slate-900);
          border-radius: var(--radius-sm);
          display: flex; align-items: center; justify-content: center;
          font-family: var(--font-mono);
          font-size: 11px; font-weight: 500;
          color: white; letter-spacing: 0.05em;
        }
        .nav-logo-name {
          font-family: var(--font-heading);
          font-size: var(--text-md);
          font-weight: 700;
          color: var(--slate-900);
        }
        .nav-actions { display: flex; gap: var(--space-3); align-items: center; }
        .nav-link {
          font-size: var(--text-sm);
          color: var(--slate-600);
          text-decoration: none;
          transition: color var(--duration-md);
        }
        .nav-link:hover { color: var(--slate-900); }

        /* ── Hero ── */
        .hero {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: var(--space-20) var(--space-8) var(--space-16);
          max-width: 800px;
          margin: 0 auto;
          width: 100%;
        }

        .hero-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: var(--space-2);
          background: var(--sage-light);
          color: #3D6B41;
          font-size: var(--text-xs);
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          padding: 5px 14px;
          border-radius: var(--radius-pill);
          margin-bottom: var(--space-6);
        }

        .hero h1 {
          font-size: clamp(2rem, 5vw, 3.25rem);
          font-weight: 700;
          letter-spacing: -0.03em;
          line-height: 1.15;
          color: var(--slate-900);
          margin-bottom: var(--space-6);
        }

        .hero h1 em {
          font-style: normal;
          color: var(--sage);
        }

        .hero-sub {
          font-size: var(--text-md);
          color: var(--slate-500);
          line-height: 1.7;
          max-width: 560px;
          margin: 0 auto var(--space-10);
        }

        .hero-cta {
          display: flex;
          gap: var(--space-3);
          justify-content: center;
          flex-wrap: wrap;
          margin-bottom: var(--space-12);
        }

        /* ── Evidence strip ── */
        .evidence-strip {
          display: flex;
          gap: var(--space-6);
          justify-content: center;
          flex-wrap: wrap;
          padding: var(--space-4) var(--space-8);
          background: var(--sand-xlight);
          border-top: 1px solid var(--sand-mid);
          border-bottom: 1px solid var(--sand-mid);
          font-size: var(--text-xs);
          color: var(--slate-500);
          font-weight: 500;
        }
        .evidence-strip span { display: flex; align-items: center; gap: 6px; }
        .evidence-dot {
          width: 7px; height: 7px;
          border-radius: 50%;
          background: var(--sage-mid);
          flex-shrink: 0;
        }

        /* ── Features ── */
        .features {
          padding: var(--space-16) var(--space-10);
          max-width: 1000px;
          margin: 0 auto;
          width: 100%;
        }
        .features-heading {
          text-align: center;
          margin-bottom: var(--space-10);
        }
        .features-heading p {
          color: var(--slate-500);
          margin-top: var(--space-3);
        }
        .features-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: var(--space-5);
        }
        .feature-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: var(--space-6);
          box-shadow: var(--shadow-xs);
          transition: box-shadow var(--duration-md), transform var(--duration-md);
        }
        .feature-card:hover {
          box-shadow: var(--shadow-md);
          transform: translateY(-2px);
        }
        .feature-icon {
          width: 40px; height: 40px;
          border-radius: var(--radius-md);
          display: flex; align-items: center; justify-content: center;
          font-size: 20px;
          margin-bottom: var(--space-4);
        }
        .feature-card h3 { font-size: var(--text-base); margin-bottom: var(--space-2); }
        .feature-card p  { font-size: var(--text-sm); color: var(--slate-500); line-height: 1.6; }

        /* ── Footer ── */
        .landing-footer {
          border-top: 1px solid var(--border);
          padding: var(--space-6) var(--space-10);
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: var(--text-xs);
          color: var(--slate-400);
        }

        /* ── Disclaimer ── */
        .disclaimer {
          background: var(--sand-xlight);
          border: 1px solid var(--sand-mid);
          border-radius: var(--radius-lg);
          padding: var(--space-4) var(--space-6);
          font-size: var(--text-xs);
          color: var(--slate-500);
          max-width: 600px;
          margin: 0 auto;
          text-align: left;
          line-height: 1.6;
        }
        .disclaimer strong { color: var(--slate-700); }
      `}</style>

      {/* Nav */}
      <nav className="landing-nav">
        <Link href="/" className="nav-logo">
          <div className="nav-logo-box">BB</div>
          <span className="nav-logo-name">Blackbox</span>
        </Link>
        <div className="nav-actions">
          <Link href="/cases" className="nav-link">Cases</Link>
          <Link href="/cases/new" className="btn btn-primary btn-sm">Open a Case</Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="hero fade-in">
        <div className="hero-eyebrow">
          <span>🛡</span>
          Meta AI Global Hackathon 2026
        </div>

        <h1>
          Road incidents deserve<br />
          <em>real investigation.</em>
        </h1>

        <p className="hero-sub">
          Blackbox turns scattered video clips and spoken accounts into a preserved,
          source-linked timeline — and lets you test specific prevention scenarios
          against the evidence.
        </p>

        <div className="hero-cta">
          <Link href="/cases/new" className="btn btn-primary btn-lg">
            Open a Case
          </Link>
          <Link href="/cases" className="btn btn-secondary btn-lg">
            View Cases
          </Link>
        </div>

        <div className="disclaimer">
          <strong>What Blackbox prepares:</strong> an investigation hypothesis with full source lineage.
          It does not determine legal fault, authenticate a video, or assert driver intent.
          When evidence is insufficient, it returns <em>undeterminable</em> — not a guess.
        </div>
      </section>

      {/* Evidence strip */}
      <div className="evidence-strip">
        <span><span className="evidence-dot" />SHA-256 integrity on every file</span>
        <span><span className="evidence-dot" />Original bytes preserved unchanged</span>
        <span><span className="evidence-dot" />Every transformation logged</span>
        <span><span className="evidence-dot" />Observed · Measured · Assumed · Simulated · Unknown</span>
      </div>

      {/* Features */}
      <section className="features">
        <div className="features-heading">
          <h2>What you get from one upload</h2>
          <p>Every output traces back to the exact frame and byte that supports it.</p>
        </div>

        <div className="features-grid">
          {[
            { icon: "🔐", bg: "var(--sage-light)",     title: "Source Preservation",     body: "Original bytes stored unchanged. SHA-256 computed during upload. Re-downloadable at any time. Hash mismatch fails hard." },
            { icon: "⏱",  bg: "var(--sky-light)",      title: "Frame-Cited Timeline",    body: "Events pinned to exact frames. Click any event to jump to the source clip. No summary without a citation." },
            { icon: "✅",  bg: "var(--sage-light)",     title: "Claim Verification",      body: "Each witness statement is checked against a video-only reconstruction. Testimony never influences the reconstruction used to check it." },
            { icon: "🔀",  bg: "var(--lavender-light)", title: "What-If Simulator",       body: "Change braking onset or approach speed. See the range of outcomes and sensitivity to assumptions — not a single confident percentage." },
            { icon: "🌐",  bg: "var(--sky-light)",      title: "3D Replay",               body: "Orbitable scene synchronized to the 2D engine. All synthetic camera angles are labelled illustrative." },
            { icon: "📄",  bg: "var(--sand-light)",     title: "Exportable Review Package", body: "PDF + JSON with original hashes, processing history, calibration, citations, and limitations. Readable without this app." },
          ].map((f) => (
            <div className="feature-card" key={f.title}>
              <div className="feature-icon" style={{ background: f.bg }}>{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <span>Blackbox · Meta Global AI Hackathon 2026</span>
        <span>Evidence-first · Not a legal tool · 1.19M road deaths/yr (WHO 2023)</span>
      </footer>
    </main>
  );
}

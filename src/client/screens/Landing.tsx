import { useState } from "react";
import { useNavigate } from "react-router-dom";

const FEATURES = [
  { icon: "◎", title: "Identity Overview", body: "Ascendant (Lagna), chart lord, Moon sign. Understand your core temperament, inner needs, and how the world perceives you." },
  { icon: "⬡", title: "Planetary Audit", body: "All 9 planets analyzed with Shadbala scores and SAV/BAV strength metrics — quantified, not generic." },
  { icon: "◈", title: "D9 Navamsha Deep Dive", body: "What D1 promises, D9 reveals. Uncover the deeper quality of each planet — true fulfillment vs. surface expression." },
  { icon: "▦", title: "All 12 House Diagnosis", body: "From House 1 (self) to House 12 (spirituality) — career, wealth, family, relationships, health, each fully diagnosed." },
  { icon: "◷", title: "Dasha Timeline", body: "Vimsottari Mahadasha + Antardasha mapping. Know which planetary period governs your life now, and what each phase brings." },
  { icon: "◉", title: "Live Generation Flow", body: "Watch your report build in real time — every analysis stage, dependency, and its progress on an interactive pipeline." }
];

const FAQS = [
  { q: "How is Vedic Astrology different from Western Astrology?", a: "Vedic Astrology (Jyotish) uses the Sidereal zodiac — aligned with actual star positions — while Western astrology uses the Tropical zodiac. The two differ by ~23°. Vedic emphasizes the Ascendant (Lagna), quantified planetary strength (Shadbala), and the Dasha time-period system for event-level predictions." },
  { q: "Do I need my exact birth time?", a: "Yes — birth time is critical for calculating your Ascendant (Lagna), the foundation of the entire chart. A 2-hour difference can shift your Ascendant to a completely different sign. Check your birth certificate or hospital records." },
  { q: "How long does report generation take?", a: "The full report is a multi-stage analysis of ~48 nodes. It runs in a few minutes; you can watch each stage complete live in the Workshop tab." }
];

export function Landing() {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState(0);
  const start = () => navigate("/new");

  return (
    <div>
      <nav>
        <div className="nav-inner">
          <div className="logo" onClick={() => navigate("/")}>Veda<span>Light</span></div>
          <button className="btn btn-gold" onClick={start}>Get My Report →</button>
        </div>
      </nav>

      <div className="hero">
        <div className="hero-tag">Parashari Jyotish · KN Rao School</div>
        <h1>Your Birth Chart,<br /><strong>Decoded with Data</strong></h1>
        <p>Enter your exact birth time and location. Receive a personalized Vedic Astrology report — quantified, structured, and generated stage by stage before your eyes.</p>
        <div className="hero-cta">
          <button className="btn btn-gold" onClick={start} style={{ padding: "14px 36px", fontSize: 15 }}>Get My Report</button>
          <button className="btn btn-outline" onClick={() => document.getElementById("sample")?.scrollIntoView({ behavior: "smooth" })} style={{ padding: "14px 28px", fontSize: 15 }}>View Sample</button>
        </div>
        <div className="hero-meta">
          <div className="hero-meta-item"><div className="num">41</div><div className="lbl">Page Report</div></div>
          <div className="hero-meta-item"><div className="num">9</div><div className="lbl">Planets Analyzed</div></div>
          <div className="hero-meta-item"><div className="num">12</div><div className="lbl">Houses Covered</div></div>
          <div className="hero-meta-item"><div className="num">D9</div><div className="lbl">Navamsha Depth</div></div>
        </div>
      </div>

      <div className="section features">
        <div className="section-inner">
          <div className="section-title">
            <h2>What's Inside <strong>Your Report</strong></h2>
            <div className="divider" />
            <p>Every section is data-backed — no generic predictions, only your chart</p>
          </div>
          <div className="grid-3">
            {FEATURES.map((f) => (
              <div className="feature-card" key={f.title}>
                <div className="feature-icon">{f.icon}</div>
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="section sample" id="sample">
        <div className="section-inner">
          <div className="section-title">
            <h2>Report <strong>Preview</strong></h2>
            <div className="divider" />
            <p>Excerpt from Section 01 of a real report</p>
          </div>
          <div className="sample-box">
            <div className="sample-label">Section 01 · Identity Overview</div>
            <div className="sample-title">Ascendant &amp; Chart Lord</div>
            <div className="sample-body">
              Your Ascendant is <strong style={{ color: "var(--gold)" }}>Capricorn</strong> at 29°45' — the final degree of Capricorn. Pragmatic, goal-driven, focused on long-term accumulation. Your chart lord is <strong style={{ color: "var(--gold)" }}>Saturn</strong>, in its own second home — House 2 Aquarius, in Own Sign dignity, operating at peak efficiency.
            </div>
            <table className="sample-table">
              <tbody>
                <tr><th>Rank</th><th>Planet</th><th>Shadbala</th><th>Status</th></tr>
                <tr><td>1</td><td>Moon</td><td>137.8%</td><td>Exalted · Taurus H5 · Emotional anchor</td></tr>
                <tr><td>2</td><td>Saturn</td><td>136.6%</td><td>Own Sign · Aquarius H2 · Chart lord at home</td></tr>
                <tr><td>3</td><td>Sun</td><td>128.6%</td><td>Neutral · Scorpio H11 · Vargottama</td></tr>
              </tbody>
            </table>
            <div className="blur-wrap">
              <div className="blur-content">
                <table className="sample-table">
                  <tbody>
                    <tr><td>4</td><td>Mercury</td><td>124.6%</td><td>Great Friend · Libra H10 · Atmakaraka</td></tr>
                    <tr><td>5</td><td>Jupiter</td><td>118.3%</td><td>Neutral · Libra H10 · Current Mahadasha lord</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="blur-overlay">
                <button className="unlock-btn" onClick={start}>Unlock Full Report →</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="section" id="pricing">
        <div className="section-inner">
          <div className="section-title">
            <h2>Choose Your <strong>Plan</strong></h2>
            <div className="divider" />
            <p>One-time · Lifetime access</p>
          </div>
          <div className="pricing-grid">
            <div className="price-card">
              <div className="price-name">Essential</div>
              <div className="price-amount">$39<span> /report</span></div>
              <div className="price-desc">Core report for those new to Vedic Astrology</div>
              <ul className="price-features">
                <li>Complete report (~30 pages)</li>
                <li>Identity overview + planetary audit</li>
                <li>All 12 house diagnoses</li>
                <li>Dasha timeline</li>
              </ul>
              <button className="btn btn-outline" style={{ width: "100%" }} onClick={start}>Choose Essential</button>
            </div>
            <div className="price-card featured">
              <div className="price-badge">Most Popular</div>
              <div className="price-name">Pro</div>
              <div className="price-amount">$79<span> /report</span></div>
              <div className="price-desc">Full depth for serious seekers</div>
              <ul className="price-features">
                <li>Complete report (41 pages)</li>
                <li>Everything in Essential</li>
                <li>D9 Navamsha deep audit</li>
                <li>Divisional cross-analysis (D10/D4/D5)</li>
                <li>Life architecture summary (10 domains)</li>
                <li>PDF export</li>
              </ul>
              <button className="btn btn-gold" style={{ width: "100%" }} onClick={start}>Choose Pro</button>
            </div>
          </div>
        </div>
      </div>

      <div className="section" style={{ background: "var(--cream-2)" }}>
        <div className="section-inner">
          <div className="section-title">
            <h2>Frequently Asked <strong>Questions</strong></h2>
            <div className="divider" />
          </div>
          <div className="faq-list">
            {FAQS.map((item, index) => (
              <div className={`faq-item ${openFaq === index ? "open" : ""}`} key={item.q}>
                <div className="faq-q" onClick={() => setOpenFaq(openFaq === index ? -1 : index)}>
                  {item.q} <span className="faq-arrow">↓</span>
                </div>
                {openFaq === index && <div className="faq-a">{item.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>

      <footer>
        <p>© 2026 <span>VedaLight</span> &nbsp;·&nbsp; Based on Parashari Jyotish | KN Rao School &nbsp;·&nbsp; For self-reflection purposes</p>
      </footer>
    </div>
  );
}

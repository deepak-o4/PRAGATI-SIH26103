import { ArrowUpRight, Check, ChevronDown, Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

const capabilities = [
  ['01', 'Project monitoring', 'Track cost, progress, timelines and execution status in one operating view.'],
  ['02', 'Risk intelligence', 'Surface schedule, cost and progress signals before they become delivery failures.'],
  ['03', 'Bottleneck analysis', 'Connect issues, milestones and dependencies to focus intervention where it matters.'],
  ['04', 'Forecasting', 'Turn current project signals into transparent completion and delay scenarios.'],
  ['05', 'Scenario analysis', 'Explore the effect of decisions before committing resources in the field.'],
  ['06', 'Decision support', 'Give delivery teams a shared, explainable picture of what needs attention next.'],
]

function HealthCard() {
  return (
    <div className="landing-visual">
      <div className="visual-orbit orbit-one" />
      <div className="visual-orbit orbit-two" />
      <div className="health-card">
        <div className="health-head"><span>PROJECT HEALTH</span><b>● LIVE VIEW</b></div>
        <h3>National Highway Expansion</h3>
        <p className="visual-muted">Portfolio signal · latest available snapshot</p>
        <div className="health-grid">
          <div><span>Physical progress</span><strong>68%</strong><i><em style={{ width: '68%' }} /></i></div>
          <div><span>Budget utilisation</span><strong>61%</strong><i><em style={{ width: '61%' }} /></i></div>
          <div><span>Schedule</span><strong className="status-watch">Watch</strong><small>+5 months</small></div>
          <div><span>Risk score</span><strong>42</strong><small>Moderate signal</small></div>
        </div>
        <div className="health-footer"><span>AI-assisted project intelligence</span><span className="signal-dot" /></div>
      </div>
      <div className="signal-card">
        <span>PROJECT INTELLIGENCE</span>
        <div><b>Cost variance</b><strong>+8.4%</strong></div>
        <div><b>AI risk signal</b><strong className="lime">Moderate</strong></div>
      </div>
      <div className="india-motif" aria-hidden="true">⌁</div>
    </div>
  )
}

export default function Landing() {
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)
  return (
    <main className="landing">
      <nav className="landing-nav">
        <Link to="/" className="landing-brand" onClick={close}><b>PRAGATI</b><span>Infrastructure intelligence</span></Link>
        <button className="landing-menu" onClick={() => setOpen(!open)} aria-label="Toggle navigation">{open ? <X /> : <Menu />}</button>
        <div className={`landing-links ${open ? 'is-open' : ''}`}>
          <a href="#platform" onClick={close}>Platform</a><a href="#intelligence" onClick={close}>Intelligence</a>
          <a href="#analytics" onClick={close}>Analytics</a><a href="#how-it-works" onClick={close}>How it works</a>
          <Link to="/login" className="nav-login" onClick={close}>Login</Link>
          <Link to="/dashboard" className="nav-dashboard" onClick={close}>Open dashboard <ArrowUpRight size={15} /></Link>
        </div>
      </nav>

      <section className="landing-hero">
        <div className="hero-copy">
          <div className="eyebrow"><span /> Infrastructure intelligence platform</div>
          <h1>See the risk.<br /><em>Before the project slips.</em></h1>
          <p>One intelligent view of infrastructure execution, cost, progress and risk — built to turn project data into decisions before delays become failures.</p>
          <div className="hero-actions"><a href="#platform" className="button button-primary">Explore PRAGATI <ArrowUpRight size={17} /></a><Link to="/dashboard" className="button button-quiet">View dashboard <ArrowUpRight size={17} /></Link></div>
          <div className="trust-line"><Check size={15} /> AI-assisted <span>•</span> Data-driven <span>•</span> Decision-ready</div>
        </div>
        <HealthCard />
      </section>

      <section className="metric-strip" aria-label="Platform highlights">
        <div><strong>01</strong><span>Unified project view</span></div><div><strong>03</strong><span>Risk dimensions</span></div>
        <div><strong>∞</strong><span>Decision pathways</span></div><div><strong>24/7</strong><span>Signal visibility</span></div>
      </section>

      <section className="landing-section intro-section" id="intelligence">
        <div className="section-label">01 / Project intelligence</div>
        <div className="intro-grid"><div><h2>From project data<br />to project decisions.</h2></div>
          <div><p>Large infrastructure programs generate enormous amounts of financial, physical and schedule information. PRAGATI brings those signals together so teams can understand what is moving, what is drifting and where intervention may be required.</p><div className="data-flow"><span>Data</span><i>↓</i><span>Project signals</span><i>↓</i><span>Risk intelligence</span><i>↓</i><b>Decision support</b></div></div>
        </div>
      </section>

      <section className="dark-section" id="platform"><div className="landing-section">
        <div className="section-label light">02 / One operating view</div><h2>One view of the entire<br /><span>project lifecycle.</span></h2>
        <div className="capability-grid">{capabilities.map(([n, title, copy]) => <article className="capability" key={n}><span>{n}</span><h3>{title}</h3><p>{copy}</p><ArrowUpRight size={20} /></article>)}</div>
      </div></section>

      <section className="landing-section cta-section" id="how-it-works"><div className="cta-card"><div className="section-label">03 / Ready when you are</div><h2>Make the next project<br /><em>more predictable.</em></h2><p>Designed around public infrastructure monitoring workflows and PAIMANA-style project data.</p><Link to="/login" className="button button-primary">Enter the workspace <ArrowUpRight size={17} /></Link></div></section>
      <footer className="landing-footer"><b>PRAGATI</b><span>AI-assisted infrastructure project intelligence</span><span>© 2026 PRAGATI</span></footer>
    </main>
  )
}

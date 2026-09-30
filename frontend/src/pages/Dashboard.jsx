import { Link } from 'react-router-dom'
import { ArrowUpRight, ChevronRight, CircleAlert, FolderKanban, Gauge, ShieldCheck } from 'lucide-react'
import { useGet } from '../hooks/useApi'
import { BarBox, RiskDistChart } from '../charts/charts'
import { DemoBanner, ErrorBox, Kpi, Loading, Page, Table, ProjectLink, RiskBadge } from '../components/ui'
import { fmtCrore, fmtNum, fmtPct } from '../utils/format'

export default function Dashboard() {
  const { data: d, error, loading } = useGet('/dashboard')
  const { data: radar } = useGet('/risk', { band: 'CRITICAL' })
  if (loading) return <Loading loading />
  if (error) return <ErrorBox error={error} />
  const k = d.kpis
  const cards = [
    ['Total projects', fmtNum(k.total_projects)], ['At risk (Warning+Critical)', fmtNum(k.projects_at_risk)], ['Critical', fmtNum(k.critical_projects)],
    ['Delayed', fmtNum(k.delayed_projects)], ['Near completion (≥90%)', fmtNum(k.projects_near_completion)],
    ['Original cost', fmtCrore(k.total_original_cost_crore)], ['Revised cost', fmtCrore(k.total_revised_cost_crore)],
    ['Expenditure', fmtCrore(k.total_expenditure_crore)], ['Avg physical progress', fmtPct(k.avg_physical_progress_pct)], ['Avg risk score', k.avg_risk_score ?? 'n/a'],
  ]
  return (
    <Page title="Executive Dashboard" sub={`Portfolio position as of ${d.as_of}`}>
      <DemoBanner show={d.demo_data_present} />
      <section className="dashboard-hero">
        <div><div className="eyebrow"><span /> Portfolio overview</div><h2>Good morning, {d.kpis.total_projects ? 'here is your' : 'your'} portfolio pulse.</h2><p>One view of project health, delivery momentum and emerging risk across the programme.</p>
          <div className="hero-actions"><Link to="/projects" className="button-primary">Explore projects <ArrowUpRight size={15} /></Link><Link to="/risk-radar" className="hero-link">Open risk radar <ChevronRight size={15} /></Link></div></div>
        <div className="hero-signal"><div className="signal-label">PORTFOLIO HEALTH</div><div className="signal-value">{k.avg_risk_score ?? 'n/a'}<span>/100</span></div><div className="signal-track"><i style={{ width: `${Math.min(100, k.avg_risk_score ?? 0)}%` }} /></div><small>Average risk score · updated {d.as_of}</small></div>
      </section>
      <div className="section-heading"><div><span className="eyebrow"><span /> At a glance</span><h2>Signals that need your attention</h2></div><Link to="/analytics">View analytics <ArrowUpRight size={14} /></Link></div>
      <div className="grid g5 dashboard-kpis">{cards.map(([l, v], i) => <Kpi key={l} label={l} value={v} sub={i === 1 ? 'across active portfolio' : undefined} />)}</div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="card chart-card"><div className="card-heading"><h2>Risk distribution</h2><span className="tag">Active projects</span></div><RiskDistChart data={d.risk_distribution} /></div>
        <div className="card chart-card"><div className="card-heading"><h2>Projects by sector</h2><span className="card-icon"><FolderKanban size={15} /></span></div><BarBox data={d.by_sector} x="key" y="projects" /></div>
        <div className="card chart-card"><div className="card-heading"><h2>Projects by ministry</h2><span className="card-icon"><ShieldCheck size={15} /></span></div><BarBox data={d.by_ministry} x="key" y="projects" horizontal /></div>
        <div className="card chart-card"><div className="card-heading"><h2>Projects by state</h2><span className="card-icon"><Gauge size={15} /></span></div><BarBox data={d.by_state} x="key" y="projects" /></div>
        <div className="card chart-card"><div className="card-heading"><h2>Physical progress</h2><span className="tag">Distribution</span></div><BarBox data={d.progress_distribution} x="bucket" y="count" /></div>
        <div className="card chart-card"><div className="card-heading"><h2>Cost overrun</h2><span className="card-icon warning"><CircleAlert size={15} /></span></div><BarBox data={d.cost_overrun_distribution} x="bucket" y="count" color="#b87542" /></div>
        <div className="card chart-card"><div className="card-heading"><h2>Schedule delay</h2><span className="card-icon warning"><CircleAlert size={15} /></span></div><BarBox data={d.schedule_delay_distribution} x="bucket" y="count" color="#b87542" /></div>
        <div className="card critical-card"><div className="card-heading"><h2>Critical projects</h2><Link to="/risk-radar">Open Risk Radar <ArrowUpRight size={14} /></Link></div>
          <Table rows={(radar?.projects || []).slice(0, 8)} empty="No critical projects." columns={[
            { key: 'project_code', label: 'Code', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'project_name', label: 'Name' },
            { key: 'risk_score', label: 'Risk', render: (r) => <RiskBadge band={r.risk_band} score={r.risk_score} /> }]} /></div>
      </div>
    </Page>
  )
}

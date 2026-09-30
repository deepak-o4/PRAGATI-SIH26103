import { useGet } from '../hooks/useApi'
import { BarBox, LineBox, RiskDistChart } from '../charts/charts'
import { DemoBanner, ErrorBox, Kpi, Loading, Page, ProjectLink, Table } from '../components/ui'
import { fmtDays, fmtNum, fmtPct } from '../utils/format'

export default function Analytics() {
  const { data: a, error, loading } = useGet('/analytics')
  if (loading) return <Loading loading />
  if (error) return <ErrorBox error={error} />
  return (
    <Page title="Infrastructure Analytics" sub="Cost, schedule, progress, risk and bottleneck analysis across the portfolio">
      <DemoBanner show={a.demo_data_present} />
      <h2>Cost</h2>
      <div className="grid g2">
        <div className="card"><h2>Original vs revised cost by sector (₹ Cr)</h2>
          <BarBox data={a.cost.by_sector.map((s) => ({ key: s.key, original: s.original_cost_crore, revised: s.revised_cost_crore }))} x="key" y="revised" color="#c62828" /><div className="note">Revised cost shown; original in table below.</div></div>
        <div className="card"><h2>Cost overrun distribution</h2><BarBox data={a.cost.distribution} x="bucket" y="count" color="#c62828" /></div>
        <div className="card"><h2>Sector cost comparison</h2><Table rows={a.cost.by_sector} columns={[{ key: 'key', label: 'Sector' }, { key: 'projects', label: 'Projects' }, { key: 'original_cost_crore', label: 'Original ₹Cr', render: (r) => fmtNum(r.original_cost_crore) }, { key: 'revised_cost_crore', label: 'Revised ₹Cr', render: (r) => fmtNum(r.revised_cost_crore) }, { key: 'avg_cost_overrun_pct', label: 'Avg overrun', render: (r) => fmtPct(r.avg_cost_overrun_pct) }]} /></div>
        <div className="card"><h2>Largest overruns</h2><Table rows={a.cost.top_overruns} columns={[{ key: 'project_code', label: 'Project', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'cost_overrun_pct', label: 'Overrun', render: (r) => fmtPct(r.cost_overrun_pct) }]} /></div>
      </div>
      <h2 style={{ marginTop: 16 }}>Schedule</h2>
      <div className="grid g2">
        <div className="card"><h2>Delay distribution</h2><BarBox data={a.schedule.distribution} x="bucket" y="count" color="#ef6c00" /></div>
        <div className="card"><h2>Projects nearing deadline (≤180 d)</h2><Kpi label="Average delay (active)" value={fmtDays(Math.round(a.schedule.avg_delay_days))} />
          <Table rows={a.schedule.nearing_deadline} columns={[{ key: 'project_code', label: 'Project', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'days_remaining', label: 'Days left' }, { key: 'physical_progress_pct', label: 'Progress', render: (r) => fmtPct(r.physical_progress_pct) }]} /></div>
      </div>
      <h2 style={{ marginTop: 16 }}>Progress</h2>
      <div className="grid g2">
        <div className="card"><h2>Physical progress distribution</h2><BarBox data={a.progress.distribution} x="bucket" y="count" /></div>
        <div className="card"><h2>Average progress by sector</h2><BarBox data={a.progress.by_sector} x="key" y="avg_progress" /><div className="note">Stagnant projects: {a.progress.stagnant_projects.length}</div></div>
      </div>
      <h2 style={{ marginTop: 16 }}>Risk</h2>
      <div className="grid g2">
        <div className="card"><h2>Risk distribution</h2><RiskDistChart data={a.risk.distribution} /></div>
        <div className="card"><h2>Average risk by sector</h2><BarBox data={a.risk.by_sector} x="key" y="avg_risk" color="#ef6c00" /></div>
        <div className="card"><h2>Average risk by ministry</h2><BarBox data={a.risk.by_ministry} x="key" y="avg_risk" horizontal color="#ef6c00" /></div>
        <div className="card"><h2>Portfolio risk trend</h2><LineBox data={a.risk.trend} x="month" domain={[0, 100]} lines={[{ key: 'avg_risk', name: 'Avg risk', color: '#c62828' }]} /><div className="note">Historical scores are reconstructed from snapshots, milestones and issues recorded as of each month.</div></div>
      </div>
      <h2 style={{ marginTop: 16 }}>Bottlenecks</h2>
      <div className="card"><Table rows={a.bottlenecks} empty="No open issues recorded." columns={[{ key: 'category', label: 'Category' }, { key: 'projects_affected', label: 'Projects' }, { key: 'open_issues', label: 'Open issues' }, { key: 'critical_issues', label: 'Critical' }, { key: 'avg_delay_days', label: 'Avg delay', render: (r) => fmtDays(r.avg_delay_days) }]} /></div>
    </Page>
  )
}

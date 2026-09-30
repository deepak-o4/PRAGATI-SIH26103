import { useState } from 'react'
import { useGet } from '../hooks/useApi'
import { ErrorBox, Kpi, Loading, Page, ProjectLink, RiskBadge, Table } from '../components/ui'
import { fmtCrore, fmtDays, fmtPct } from '../utils/format'

export default function RiskRadar() {
  const [f, setF] = useState({ band: '', sector: '', line_ministry: '', implementing_agency: '', state: '', min_cost: '', min_delay_days: '', max_progress: '' })
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
  const { data, error, loading } = useGet('/risk', params)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <Page title="Risk Radar" sub="Active projects ranked by explainable risk score. Open a project to see why.">
      <div className="filters">
        <select aria-label="Band" value={f.band} onChange={set('band')}><option value="">All bands</option>{['CRITICAL', 'WARNING', 'WATCH', 'STABLE'].map((b) => <option key={b}>{b}</option>)}</select>
        {['sector', 'line_ministry', 'implementing_agency', 'state'].map((k) => <input key={k} placeholder={k.replace('_', ' ')} aria-label={k} value={f[k]} onChange={set(k)} />)}
        <input type="number" min="0" placeholder="Min cost (₹ Cr)" aria-label="Min cost" value={f.min_cost} onChange={set('min_cost')} />
        <input type="number" min="0" placeholder="Min delay (days)" aria-label="Min delay" value={f.min_delay_days} onChange={set('min_delay_days')} />
        <input type="number" min="0" max="100" placeholder="Max progress %" aria-label="Max progress" value={f.max_progress} onChange={set('max_progress')} />
      </div>
      <ErrorBox error={error} /><Loading loading={loading} />
      {data && <>
        <div className="grid g5">{['CRITICAL', 'WARNING', 'WATCH', 'STABLE'].map((b) => <Kpi key={b} label={b} value={data.counts[b]} />)}</div>
        <div className="card" style={{ marginTop: 12 }}>
          <Table rows={data.projects} columns={[
            { key: 'risk_score', label: 'Risk', render: (r) => <RiskBadge band={r.risk_band} score={r.risk_score} /> },
            { key: 'project_code', label: 'Code', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'project_name', label: 'Project' },
            { key: 'sector', label: 'Sector' }, { key: 'state', label: 'State' },
            { key: 'physical_progress_pct', label: 'Progress', render: (r) => fmtPct(r.physical_progress_pct) },
            { key: 'schedule_delay_days', label: 'Delay', render: (r) => fmtDays(r.schedule_delay_days) },
            { key: 'cost_overrun_pct', label: 'Overrun', render: (r) => fmtPct(r.cost_overrun_pct) },
            { key: 'revised_cost_crore', label: 'Cost', render: (r) => fmtCrore(r.revised_cost_crore ?? r.original_cost_crore) }]} />
          {data.truncated && <div className="note">Showing the top 500 by risk; narrow the filters to see others.</div>}
        </div></>}
    </Page>
  )
}

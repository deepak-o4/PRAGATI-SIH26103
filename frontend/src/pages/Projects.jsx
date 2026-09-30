import { useState } from 'react'
import { useGet } from '../hooks/useApi'
import { ErrorBox, Loading, Page, ProgressBar, ProjectLink, RiskBadge, Table } from '../components/ui'
import { fmtCrore, fmtPct } from '../utils/format'

export default function Projects() {
  const [f, setF] = useState({ q: '', sector: '', state: '', risk_level: '', page: 1, sort: 'risk_score', order: 'desc' })
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
  const { data, error, loading } = useGet('/projects', { ...params, page_size: 25 })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, page: 1 })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <Page title="Projects" sub="Project explorer — click a project to open its cockpit">
      <div className="filters">
        <input placeholder="Search name or code" aria-label="Search" value={f.q} onChange={set('q')} />
        <input placeholder="Sector" aria-label="Sector" value={f.sector} onChange={set('sector')} />
        <input placeholder="State" aria-label="State" value={f.state} onChange={set('state')} />
        <select aria-label="Risk level" value={f.risk_level} onChange={set('risk_level')}><option value="">Any risk</option>{['CRITICAL', 'WARNING', 'WATCH', 'STABLE'].map((b) => <option key={b}>{b}</option>)}</select>
        <select aria-label="Sort" value={f.sort} onChange={set('sort')}>{['risk_score', 'project_code', 'physical_progress_pct', 'original_cost_crore', 'revised_cost_crore'].map((s) => <option key={s}>{s}</option>)}</select>
      </div>
      <ErrorBox error={error} /><Loading loading={loading} />
      {data && <div className="card"><Table rows={data.items} columns={[
        { key: 'project_code', label: 'Code', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'project_name', label: 'Project' },
        { key: 'sector', label: 'Sector' }, { key: 'state', label: 'State' }, { key: 'status', label: 'Status', render: (r) => <span className="tag">{r.status}</span> },
        { key: 'physical_progress_pct', label: 'Progress', render: (r) => <><ProgressBar value={r.physical_progress_pct} /><span className="note">{fmtPct(r.physical_progress_pct)}</span></> },
        { key: 'revised_cost_crore', label: 'Revised cost', render: (r) => fmtCrore(r.revised_cost_crore ?? r.original_cost_crore) },
        { key: 'risk_score', label: 'Risk', render: (r) => <RiskBadge band={r.risk_level} score={r.risk_score} /> },
        { key: 'origin', label: 'Origin', render: (r) => <span className="tag">{r.origin}</span> }]} />
        <div className="filters" style={{ marginTop: 10 }}>
          <button className="sec" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })}>Prev</button>
          <span className="note">Page {f.page} of {pages} · {data.total} projects</span>
          <button className="sec" disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })}>Next</button>
        </div></div>}
    </Page>
  )
}

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import api, { errMsg } from '../services/api'
import { useGet } from '../hooks/useApi'
import { useAuth } from '../services/auth'
import { LineBox } from '../charts/charts'
import { DemoBanner, ErrorBox, Kpi, Loading, Page, ProgressBar, RiskBadge, Table, Tabs } from '../components/ui'
import { fmtCrore, fmtDate, fmtDays, fmtNum, fmtPct } from '../utils/format'

function RiskPanel({ risk }) {
  const cur = risk.current
  const max = Math.max(1, ...cur.contributors.map((c) => c.weight_pct))
  return (
    <div className="card">
      <h2>Why this score? <RiskBadge band={cur.band} score={cur.score} /></h2>
      {cur.contributors.map((c) => (
        <div className="contrib" key={c.key} title={c.explanation}>
          <span>{c.label}</span>
          <div className="bar"><i style={{ width: `${(c.points / max) * 100}%`, background: c.available ? '#3f7cc4' : '#c5cdd8' }} /></div>
          <b>{c.available ? `+${c.points}` : 'n/a'}</b>
        </div>
      ))}
      <table style={{ marginTop: 8 }}><thead><tr><th>Component</th><th>Weight</th><th>Sub-score</th><th>Points</th><th>Basis</th></tr></thead><tbody>
        {cur.contributors.map((c) => <tr key={c.key}><td>{c.label}</td><td>{c.weight_pct}%</td><td>{c.subscore ?? 'n/a'}</td><td>{c.points}</td><td>{c.explanation}</td></tr>)}
        <tr><td colSpan="3"><b>Total</b></td><td colSpan="2"><b>{cur.score}</b> ({cur.version})</td></tr></tbody></table>
      {cur.notes?.map((n) => <div className="note" key={n}>{n}</div>)}
      <div className="note">{risk.disclaimer}</div>
    </div>
  )
}

function ScenarioPanel({ code }) {
  const { canAnalyse } = useAuth()
  const [adj, setAdj] = useState({ progress_increase_pts: 0, completion_slip_days: 0, milestone_delay_days: 0, revised_cost_increase_pct: 0, resolve_all_critical: false, recovery_days_assumed: 0 })
  const [res, setRes] = useState(null); const [err, setErr] = useState(null)
  const num = (k) => (e) => setAdj({ ...adj, [k]: Number(e.target.value) })
  const run = async (save = false) => { setErr(null); try { setRes((await api.post(`/projects/${code}/scenarios`, { ...adj, save, name: 'Cockpit scenario' })).data) } catch (e) { setErr(errMsg(e)) } }
  return (
    <div className="card"><h2>What-if simulation</h2>
      <div className="note">Simulation only — not an official government forecast.</div>
      <div className="filters" style={{ marginTop: 8 }}>
        <label>Progress +pts <input type="number" min="0" max="100" value={adj.progress_increase_pts} onChange={num('progress_increase_pts')} /></label>
        <label>Completion slip (days) <input type="number" min="0" value={adj.completion_slip_days} onChange={num('completion_slip_days')} /></label>
        <label>Milestone delay (days) <input type="number" min="0" value={adj.milestone_delay_days} onChange={num('milestone_delay_days')} /></label>
        <label>Revised cost +% <input type="number" min="0" value={adj.revised_cost_increase_pct} onChange={num('revised_cost_increase_pct')} /></label>
        <label><input type="checkbox" checked={adj.resolve_all_critical} onChange={(e) => setAdj({ ...adj, resolve_all_critical: e.target.checked })} /> Resolve all critical issues</label>
        <label>Assumed recovery (days) <input type="number" min="0" value={adj.recovery_days_assumed} onChange={num('recovery_days_assumed')} /></label>
        <button disabled={!canAnalyse} onClick={() => run(false)}>Run scenario</button>
        <button className="sec" disabled={!canAnalyse} onClick={() => run(true)}>Run &amp; save</button>
      </div>
      <ErrorBox error={err} />
      {res && <div>
        <div className="grid g5">
          <Kpi label="Current risk" value={res.baseline.risk_score} sub={res.baseline.risk_band} />
          <Kpi label="Projected risk" value={res.projected.risk_score} sub={res.projected.risk_band} />
          <Kpi label="Risk change" value={res.delta.risk_score > 0 ? `+${res.delta.risk_score}` : res.delta.risk_score} />
          <Kpi label="Forecast delay change" value={res.delta.forecast_delay_days == null ? 'n/a' : fmtDays(res.delta.forecast_delay_days)} />
        </div>
        {res.assumptions.map((a) => <div className="note" key={a}>Assumption: {a}</div>)}
        {res.warnings.map((w) => <div className="err" key={w}>{w}</div>)}
        <div className="note">{res.label}</div></div>}
    </div>
  )
}

function Actions({ code }) {
  const { canWrite } = useAuth()
  const { data, reload } = useGet(`/projects/${code}/actions`)
  const [f, setF] = useState({ title: '', owner: '', due_date: '', priority: 'MEDIUM' }); const [err, setErr] = useState(null)
  const add = async (e) => { e.preventDefault(); setErr(null)
    try { await api.post(`/projects/${code}/actions`, { ...f, due_date: f.due_date || null }); setF({ title: '', owner: '', due_date: '', priority: 'MEDIUM' }); reload() } catch (x) { setErr(errMsg(x)) } }
  return (
    <div className="card"><h2>Interventions</h2>
      <Table rows={data} empty="No actions recorded yet." columns={[{ key: 'title', label: 'Action' }, { key: 'owner', label: 'Owner' }, { key: 'priority', label: 'Priority' }, { key: 'due_date', label: 'Due', render: (r) => fmtDate(r.due_date) }, { key: 'status', label: 'Status' }]} />
      {canWrite && <form className="filters" onSubmit={add} style={{ marginTop: 10 }}>
        <input required placeholder="Recommended intervention" aria-label="Action" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} style={{ minWidth: 260 }} />
        <input placeholder="Owner" aria-label="Owner" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} />
        <input type="date" aria-label="Due date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
        <select aria-label="Priority" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((p) => <option key={p}>{p}</option>)}</select>
        <button>Create intervention</button></form>}
      <ErrorBox error={err} />
    </div>
  )
}

export default function ProjectCockpit() {
  const { code } = useParams()
  const [tab, setTab] = useState('Overview')
  const p = useGet(`/projects/${code}`); const snaps = useGet(`/projects/${code}/snapshots`); const risk = useGet(`/projects/${code}/risk`)
  const ms = useGet(`/projects/${code}/milestones`); const iss = useGet(`/projects/${code}/issues`); const fc = useGet(`/projects/${code}/forecast`)
  if (p.loading) return <Loading loading />
  if (p.error) return <ErrorBox error={p.error} />
  const d = p.data
  const series = (snaps.data || []).map((s) => ({ month: s.snapshot_month.slice(0, 7), physical: s.physical_progress_pct, financial: s.financial_progress_pct, expenditure: s.cumulative_expenditure_crore, revised: s.revised_cost_crore }))
  const riskSeries = (risk.data?.history || []).map((h) => ({ month: h.month.slice(0, 7), risk: h.score }))
  const openIssues = (iss.data || []).filter((i) => ['OPEN', 'IN_PROGRESS'].includes(i.status))
  const byType = Object.entries(openIssues.reduce((a, i) => ({ ...a, [i.issue_type]: (a[i.issue_type] || 0) + 1 }), {}))
  const f = fc.data?.forecast; const pred = fc.data?.delay_prediction
  return (
    <Page title={d.project_name} sub={`${d.project_code} · ${d.sector ?? 'n/a'} · ${d.line_ministry ?? 'n/a'} · ${d.implementing_agency ?? 'n/a'} · ${d.state ?? 'n/a'}`}>
      <DemoBanner show={d.origin === 'SYNTHETIC_DEMO'} />
      <div className="filters"><span className="tag">{d.status}</span><RiskBadge band={d.risk_band} score={d.risk_score} /><span className="tag">Origin: {d.origin}</span>
        <a href={`/api/v1/reports/project/${encodeURIComponent(d.project_code)}`} onClick={async (e) => { e.preventDefault(); const r = await api.get(`/reports/project/${d.project_code}`, { responseType: 'blob' }); window.open(URL.createObjectURL(r.data)) }}>Project review PDF</a></div>
      <div className="grid g5">
        <Kpi label="Original cost" value={fmtCrore(d.original_cost_crore)} /><Kpi label="Revised cost" value={fmtCrore(d.revised_cost_crore)} sub={d.cost_overrun_pct != null ? `${fmtPct(d.cost_overrun_pct)} vs original` : 'overrun unavailable'} />
        <Kpi label="Expenditure" value={fmtCrore(d.cumulative_expenditure_crore)} sub={d.expenditure_ratio_pct != null ? `${fmtPct(d.expenditure_ratio_pct)} of cost` : ''} />
        <Kpi label="Physical progress" value={fmtPct(d.physical_progress_pct)} /><Kpi label="Financial progress" value={fmtPct(d.financial_progress_pct)} />
        <Kpi label="Schedule delay" value={fmtDays(d.schedule_delay_days)} sub={`official slip ${fmtDays(d.revised_slip_days)} · overdue ${fmtDays(d.overdue_days)}`} />
        <Kpi label="Days remaining" value={fmtNum(d.days_remaining)} sub={d.deadline_proximity} /><Kpi label="Risk score" value={d.risk_score ?? 'n/a'} sub={`${fmtPct(d.assessed_weight_pct, 0)} of weight assessable`} />
      </div>
      {d.imbalance_flag && <div className="demo" style={{ marginTop: 12 }}>Expenditure is {fmtNum(d.cost_progress_imbalance_pts)} pts ahead of physical progress. This is an analytical indicator for review, not a finding of misuse.</div>}
      <div style={{ marginTop: 12 }}><Tabs tabs={['Overview', 'Risk', 'Milestones', 'Issues', 'Forecast', 'Scenario', 'Actions']} value={tab} onChange={setTab} /></div>
      {tab === 'Overview' && <div className="grid g2">
        <div className="card"><h2>Progress timeline (%)</h2><LineBox data={series} x="month" domain={[0, 100]} lines={[{ key: 'physical', name: 'Physical', color: '#1f3a5f' }, { key: 'financial', name: 'Financial', color: '#ef6c00' }]} /></div>
        <div className="card"><h2>Cost &amp; expenditure timeline (₹ Cr)</h2><LineBox data={series} x="month" lines={[{ key: 'expenditure', name: 'Expenditure', color: '#ef6c00' }, { key: 'revised', name: 'Revised cost', color: '#c62828' }]} /></div>
        <div className="card"><h2>Risk timeline</h2><LineBox data={riskSeries} x="month" domain={[0, 100]} lines={[{ key: 'risk', name: 'Risk score', color: '#c62828' }]} />
          <div className="note">Reconstructed from information recorded up to each month.</div></div>
        <div className="card"><h2>Snapshot history</h2><Table rows={[...(snaps.data || [])].reverse().slice(0, 12)} columns={[{ key: 'snapshot_month', label: 'Month', render: (r) => r.snapshot_month.slice(0, 7) }, { key: 'physical_progress_pct', label: 'Physical', render: (r) => fmtPct(r.physical_progress_pct) }, { key: 'cumulative_expenditure_crore', label: 'Expenditure', render: (r) => fmtCrore(r.cumulative_expenditure_crore) }, { key: 'origin', label: 'Origin' }]} /></div>
      </div>}
      {tab === 'Risk' && (risk.data ? <RiskPanel risk={risk.data} /> : <Loading loading />)}
      {tab === 'Milestones' && <div className="card"><h2>Milestone timeline</h2><Table rows={ms.data} empty="No milestones recorded." columns={[{ key: 'name', label: 'Milestone' }, { key: 'planned_end', label: 'Planned end', render: (r) => fmtDate(r.planned_end) }, { key: 'actual_end', label: 'Actual end', render: (r) => fmtDate(r.actual_end) }, { key: 'completion_pct', label: 'Done', render: (r) => <><ProgressBar value={r.completion_pct} /></> }, { key: 'delay_days', label: 'Delay', render: (r) => fmtDays(r.delay_days) }, { key: 'status', label: 'Status' }, { key: 'depends_on', label: 'Depends on' }]} /></div>}
      {tab === 'Issues' && <div className="grid g2"><div className="card"><h2>Open issues ({openIssues.length}) · Critical {openIssues.filter((i) => i.severity === 'CRITICAL').length}</h2>
        <Table rows={iss.data} empty="No issues recorded." columns={[{ key: 'issue_type', label: 'Type' }, { key: 'severity', label: 'Severity' }, { key: 'status', label: 'Status' }, { key: 'description', label: 'Description' }, { key: 'expected_resolution_date', label: 'Expected', render: (r) => fmtDate(r.expected_resolution_date) }, { key: 'owner', label: 'Owner' }]} /></div>
        <div className="card"><h2>Open issue categories</h2>{byType.length ? byType.map(([k, v]) => <div key={k}>{k}: <b>{v}</b></div>) : <div className="note">None open.</div>}</div></div>}
      {tab === 'Forecast' && <div className="grid g2">
        <div className="card"><h2>Completion forecast <span className="tag">PREDICTED</span></h2>
          {f ? <><div>Official revised completion: <b>{fmtDate(f.official_revised_end_date)}</b></div>
            <div>PRAGATI predicted completion: <b>{f.predicted_completion_date ? fmtDate(f.predicted_completion_date) : 'not available'}</b></div>
            <div>Estimated delay vs official: <b>{fmtDays(f.estimated_delay_days)}</b></div>
            <div>Confidence: <b>{f.confidence_label}</b> {f.confidence != null && `(${f.confidence})`}</div>
            <div className="note">Status: {f.status}. {f.reasons.join(' ')}</div></> : <Loading loading />}
          <div className="note">{fc.data?.note}</div></div>
        <div className="card"><h2>Delay prediction <span className="tag">PREDICTED</span></h2>
          {pred ? <><div>Delay probability: <b>{Math.round(pred.delay_probability * 100)}%</b> <span className="tag">{pred.model_version}</span></div>
            {!pred.calibrated && <div className="note">Not a calibrated probability. {pred.note}</div>}
            <h2 style={{ marginTop: 10 }}>Top factors</h2>
            {pred.top_factors.map((t) => <div key={t.feature}>{t.direction} {t.feature} <span className="note">({t.impact})</span></div>)}</> : <Loading loading />}</div></div>}
      {tab === 'Scenario' && <ScenarioPanel code={code} />}
      {tab === 'Actions' && <Actions code={code} />}
    </Page>
  )
}

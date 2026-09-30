import { Link } from 'react-router-dom'
import { BAND_COLORS } from '../utils/format'

export const RiskBadge = ({ band, score }) => band
  ? <span className={`badge b-${band}`} title={`Risk band ${band}`}>{band}{score != null ? ` · ${Math.round(score)}` : ''}</span>
  : <span className="tag">n/a</span>

export const Kpi = ({ label, value, sub }) => (
  <div className="card kpi"><div className="l">{label}</div><div className="v">{value}</div>{sub && <div className="note">{sub}</div>}</div>
)

export const DemoBanner = ({ show }) => show
  ? <div className="demo" role="status"><b>Demo Data.</b> This portfolio includes SYNTHETIC_DEMO records. They are not official government data.</div>
  : null

export const ErrorBox = ({ error }) => error ? <div className="err" role="alert">{error}</div> : null
export const Loading = ({ loading }) => loading ? <div className="note">Loading…</div> : null

export const ProgressBar = ({ value }) => (
  <div className="bar" role="progressbar" aria-valuenow={value ?? 0} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${Math.min(100, value ?? 0)}%` }} /></div>
)

export const ProjectLink = ({ code, children }) => <Link to={`/projects/${encodeURIComponent(code)}`}>{children || code}</Link>

export const Page = ({ title, sub, children }) => (<div><h1>{title}</h1>{sub && <div className="sub">{sub}</div>}{children}</div>)

export function Table({ columns, rows, empty = 'No records.' }) {
  if (!rows || rows.length === 0) return <div className="note">{empty}</div>
  return (
    <div className="scroll"><table><thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.id || r.project_code + i}>{columns.map((c) => <td key={c.key}>{c.render ? c.render(r) : (r[c.key] ?? 'n/a')}</td>)}</tr>)}</tbody></table></div>
  )
}

export const Tabs = ({ tabs, value, onChange }) => (
  <div className="tabs" role="tablist">{tabs.map((t) => <button key={t} role="tab" aria-selected={value === t} className={value === t ? 'on' : ''} onClick={() => onChange(t)}>{t}</button>)}</div>
)

export const bandColor = (b) => BAND_COLORS[b] || '#888'

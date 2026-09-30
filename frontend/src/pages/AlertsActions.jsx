import { useState } from 'react'
import api, { errMsg } from '../services/api'
import { useGet } from '../hooks/useApi'
import { useAuth } from '../services/auth'
import { ErrorBox, Loading, Page, ProjectLink, Table } from '../components/ui'
import { fmtDate } from '../utils/format'

export function Alerts() {
  const { data, error, loading, reload } = useGet('/alerts')
  const [err, setErr] = useState(null)
  const ack = async (id) => { try { await api.post(`/alerts/${id}/ack`); reload() } catch (e) { setErr(errMsg(e)) } }
  return (
    <Page title="Alerts" sub="Raised when risk worsens, progress stagnates or expenditure runs ahead of progress">
      <ErrorBox error={error || err} /><Loading loading={loading} />
      <div className="card"><Table rows={data} empty="No unacknowledged alerts." columns={[
        { key: 'created_at', label: 'When', render: (r) => fmtDate(r.created_at) }, { key: 'severity', label: 'Severity' }, { key: 'kind', label: 'Type' },
        { key: 'project_code', label: 'Project', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'message', label: 'Message' },
        { key: 'id', label: '', render: (r) => <button className="sec" onClick={() => ack(r.id)}>Acknowledge</button> }]} /></div>
    </Page>
  )
}

export function Actions() {
  const { canWrite } = useAuth()
  const [status, setStatus] = useState('')
  const { data, error, loading, reload } = useGet('/actions', status ? { status } : {})
  const [err, setErr] = useState(null)
  const setS = async (id, s) => { try { await api.patch(`/actions/${id}`, { status: s }); reload() } catch (e) { setErr(errMsg(e)) } }
  return (
    <Page title="Actions" sub="Interventions across all projects. Create them from a project cockpit.">
      <div className="filters"><select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{['OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED'].map((s) => <option key={s}>{s}</option>)}</select></div>
      <ErrorBox error={error || err} /><Loading loading={loading} />
      <div className="card"><Table rows={data} empty="No actions." columns={[
        { key: 'title', label: 'Action' }, { key: 'project_code', label: 'Project', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'owner', label: 'Owner' },
        { key: 'priority', label: 'Priority' }, { key: 'due_date', label: 'Due', render: (r) => fmtDate(r.due_date) }, { key: 'status', label: 'Status' },
        { key: 'id', label: '', render: (r) => canWrite && r.status !== 'DONE' ? <button className="sec" onClick={() => setS(r.id, r.status === 'OPEN' ? 'IN_PROGRESS' : 'DONE')}>{r.status === 'OPEN' ? 'Start' : 'Mark done'}</button> : null }]} /></div>
    </Page>
  )
}

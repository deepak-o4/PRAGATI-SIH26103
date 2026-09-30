import { useState } from 'react'
import api, { errMsg } from '../services/api'
import { useGet } from '../hooks/useApi'
import { useAuth } from '../services/auth'
import { ErrorBox, Kpi, Loading, Page, Table } from '../components/ui'
import { fmtDate } from '../utils/format'

export default function DataPage() {
  const { canWrite, canAnalyse } = useAuth()
  const dq = useGet('/data-quality'); const hist = useGet('/ingestion/history'); const docs = useGet('/documents')
  const [kind, setKind] = useState('projects'); const [origin, setOrigin] = useState('USER_UPLOADED'); const [name, setName] = useState(''); const [url, setUrl] = useState('')
  const [file, setFile] = useState(null); const [report, setReport] = useState(null); const [err, setErr] = useState(null); const [busy, setBusy] = useState(false)
  const [doc, setDoc] = useState(null); const [docCode, setDocCode] = useState('')
  const upload = async (e) => {
    e.preventDefault(); if (!file) return; setErr(null); setBusy(true)
    const fd = new FormData(); fd.append('file', file); fd.append('origin', origin); fd.append('source_name', name || file.name); if (url) fd.append('source_url', url)
    try { setReport((await api.post(`/ingestion/${kind}`, fd)).data.report); dq.reload(); hist.reload() } catch (x) { setErr(errMsg(x)) } finally { setBusy(false) }
  }
  const uploadDoc = async (e) => {
    e.preventDefault(); if (!doc) return; setErr(null)
    const fd = new FormData(); fd.append('file', doc); if (docCode) fd.append('project_code', docCode)
    try { await api.post('/documents', fd); docs.reload() } catch (x) { setErr(errMsg(x)) }
  }
  const q = dq.data
  return (
    <Page title="Data" sub="Data quality, ingestion and source transparency">
      <ErrorBox error={err || dq.error} /><Loading loading={dq.loading} />
      {q && <div className="grid g5"><Kpi label="Total records" value={q.total_records} /><Kpi label="Completeness" value={q.completeness_score_pct == null ? 'n/a' : `${q.completeness_score_pct}%`} sub={q.definition} />
        <Kpi label="Duplicate codes" value={q.duplicate_project_codes} /><Kpi label="Invalid dates" value={q.invalid_dates} /><Kpi label="Invalid costs" value={q.invalid_costs} />
        <Kpi label="Invalid progress" value={q.invalid_progress_values} /><Kpi label="Missing codes" value={q.missing_project_codes} /><Kpi label="< 2 snapshots" value={q.projects_with_fewer_than_2_snapshots} /></div>}
      {q && <div className="card" style={{ marginTop: 12 }}><h2>Missing values by field</h2><Table rows={Object.entries(q.missing_values_by_field).map(([field, missing]) => ({ id: field, field, missing }))} columns={[{ key: 'field', label: 'Field' }, { key: 'missing', label: 'Missing' }]} /></div>}
      {canWrite && <div className="card" style={{ marginTop: 12 }}><h2>Ingest data (CSV / XLSX)</h2>
        <form className="filters" onSubmit={upload}>
          <select aria-label="Dataset" value={kind} onChange={(e) => setKind(e.target.value)}>{['projects', 'snapshots', 'milestones', 'issues'].map((k) => <option key={k}>{k}</option>)}</select>
          <select aria-label="Origin" value={origin} onChange={(e) => setOrigin(e.target.value)}>{['USER_UPLOADED', 'IMPORTED', 'OFFICIAL', 'SYNTHETIC_DEMO'].map((k) => <option key={k}>{k}</option>)}</select>
          <input placeholder="Source name" aria-label="Source name" value={name} onChange={(e) => setName(e.target.value)} /><input placeholder="Source URL" aria-label="Source URL" value={url} onChange={(e) => setUrl(e.target.value)} />
          <input type="file" accept=".csv,.xlsx" aria-label="File" onChange={(e) => setFile(e.target.files[0])} /><button disabled={busy || !file}>{busy ? 'Importing…' : 'Import'}</button></form>
        <div className="note">Load projects first, then snapshots, milestones and issues (they reference project codes). Invalid rows are rejected with reasons; missing values stay empty.</div>
        {report && <div style={{ marginTop: 8 }}><b>{report.accepted}</b> of {report.total_rows} rows accepted · <b>{report.rejected.length}</b> rejected
          {report.unmapped_columns?.length > 0 && <div className="note">Unmapped optional columns: {report.unmapped_columns.join(', ')}</div>}
          {report.warnings?.slice(0, 10).map((w) => <div className="note" key={w}>⚠ {w}</div>)}
          {report.rejected.length > 0 && <Table rows={report.rejected.slice(0, 50).map((r, i) => ({ id: i, ...r, errors: r.errors.join('; ') }))} columns={[{ key: 'row', label: 'Row' }, { key: 'project_code', label: 'Code' }, { key: 'errors', label: 'Reason' }]} />}</div>}</div>}
      <div className="card" style={{ marginTop: 12 }}><h2>Data sources</h2><Table rows={hist.data} empty="No imports yet." columns={[{ key: 'created_at', label: 'When', render: (r) => fmtDate(r.created_at) }, { key: 'source_name', label: 'Source' }, { key: 'origin', label: 'Origin', render: (r) => <span className="tag">{r.origin}</span> }, { key: 'source_document', label: 'Document' }, { key: 'source_url', label: 'URL' }, { key: 'record_counts', label: 'Counts', render: (r) => JSON.stringify(r.record_counts) }]} /></div>
      <div className="card" style={{ marginTop: 12 }}><h2>Project documents (PDF, DOCX, XLSX, CSV, TXT)</h2>
        {canAnalyse && <form className="filters" onSubmit={uploadDoc}><input type="file" accept=".pdf,.docx,.xlsx,.csv,.txt" aria-label="Document" onChange={(e) => setDoc(e.target.files[0])} />
          <input placeholder="Project code (optional)" aria-label="Project code" value={docCode} onChange={(e) => setDocCode(e.target.value)} /><button disabled={!doc}>Upload</button></form>}
        <Table rows={docs.data} empty="No documents." columns={[{ key: 'filename', label: 'File' }, { key: 'created_at', label: 'Uploaded', render: (r) => fmtDate(r.created_at) }, { key: 'entities', label: 'Extracted (candidates)', render: (r) => `${r.entities?.dates?.length || 0} dates, ${r.entities?.costs?.length || 0} costs, ${r.entities?.project_references?.length || 0} project refs` }]} />
        <div className="note">Extraction is regex-based and produces candidates only; nothing is written into project data automatically.</div></div>
    </Page>
  )
}

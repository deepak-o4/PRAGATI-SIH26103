import { useState } from 'react'
import api, { errMsg } from '../services/api'
import { ErrorBox, Page } from '../components/ui'

export default function Reports() {
  const [err, setErr] = useState(null); const [busy, setBusy] = useState('')
  const [code, setCode] = useState('')
  const download = async (url, name, key) => {
    setErr(null); setBusy(key)
    try {
      const r = await api.get(url, { responseType: 'blob' })
      const a = document.createElement('a'); a.href = URL.createObjectURL(r.data); a.download = name; a.click(); URL.revokeObjectURL(a.href)
    } catch (e) { setErr(e?.response?.data instanceof Blob ? 'Report generation failed' : errMsg(e)) } finally { setBusy('') }
  }
  return (
    <Page title="Reports" sub="Executive and project review reports. Reports carry a demo-data banner when synthetic records are present.">
      <ErrorBox error={err} />
      <div className="grid g2">
        <div className="card"><h2>Executive Review Report</h2>
          <p className="note">Portfolio summary, critical projects, risk distribution, cost overruns, schedule delays, bottlenecks and open actions.</p>
          {['pdf', 'xlsx', 'csv'].map((f) => <button key={f} style={{ marginRight: 8 }} disabled={!!busy} onClick={() => download(`/reports/executive?format=${f}`, `pragati-executive.${f}`, f)}>{busy === f ? 'Generating…' : f.toUpperCase()}</button>)}</div>
        <div className="card"><h2>Project Review Report (PDF)</h2>
          <div className="filters"><input placeholder="Project code" aria-label="Project code" value={code} onChange={(e) => setCode(e.target.value)} />
            <button disabled={!code || !!busy} onClick={() => download(`/reports/project/${encodeURIComponent(code)}`, `pragati-${code}.pdf`, 'proj')}>Generate</button></div></div>
      </div>
    </Page>
  )
}
